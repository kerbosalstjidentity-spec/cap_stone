"""
Kafka 거래 요청 수신 (fraud.transaction.requested).

Spring Boot이 발행한 메시지를 소비하여 /v1/fraud/evaluate 로직을 직접 실행.
HTTP 호출 없이 내부 함수 재활용 → 레이턴시 최소화.

W4-#3: _process_message 는 sync CPU 함수 — `asyncio.to_thread` 로 감싸 이벤트루프 블로킹 제거.
W4-#4: 처리 실패 시 DLQ 발행 + consumer 자체 재시작 워치독.
W4-#7: partition key=user_id (producer 측에서 처리, consumer 는 그대로 수신).

메시지 스키마 (JSON):
{
  "tx_id": "...",
  "user_id": "...",
  "score": 0.85,
  "amount": 150000,
  ...
}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

try:
    from aiokafka import AIOKafkaConsumer
    _HAS_AIOKAFKA = True
except ImportError:
    _HAS_AIOKAFKA = False

from app.kafka import producer as kafka_producer
from app.kafka.config import (
    AUTO_OFFSET_RESET,
    CONSUMER_GROUP,
    CONSUMER_RESTART_BACKOFF_S,
    KAFKA_BOOTSTRAP,
    TOPIC_TX_REQUEST,
)

logger = logging.getLogger(__name__)

_supervisor_task: asyncio.Task | None = None
_stop_requested = False


def _process_message(data: dict[str, Any]) -> dict[str, Any]:
    """메시지 처리 — fraud_service 내부 로직 직접 호출 (sync, CPU/IO 혼재)."""
    # 순환 임포트 방지를 위해 함수 내부에서 임포트
    from app.services.fraud_service import FraudServiceManager
    from app.services.profile_store import profile_store
    from app.services.rule_engine import rule_engine
    from app.services.stats_collector import stats_collector

    tx = data
    profile = profile_store.get_profile(tx.get("user_id", ""))
    rule_results = rule_engine.evaluate_all(tx, profile)
    rule_action, rule_ids = rule_engine.get_strongest(rule_results)

    manager = FraudServiceManager(tx)
    final_action = manager.get_final_action()

    # W5.5-#8: 평가 직후 profile 갱신 — REST evaluate 와 동일 정책
    user_id_for_ingest = tx.get("user_id", "")
    if user_id_for_ingest:
        try:
            profile_store.ingest(user_id_for_ingest, tx)
        except Exception:
            pass

    # W6.5-#1: 송금 그래프 store 적재 — sender/receiver 모두 있는 경우
    receiver = tx.get("nameDest") or tx.get("receiver_id") or ""
    if user_id_for_ingest and receiver:
        try:
            from app.services.graph_store import graph_store
            graph_store.record(
                sender=user_id_for_ingest,
                receiver=str(receiver),
                amount=float(tx.get("amount", 0) or 0),
                tx_id=str(tx.get("tx_id", "") or ""),
            )
        except Exception:
            pass

    triggered = rule_ids.split(",") if rule_ids else []
    stats_collector.record(
        tx.get("tx_id", ""),
        final_action,
        triggered,
        float(tx.get("score", 0)),
        float(tx.get("amount", 0)),
    )

    return {
        "tx_id": tx.get("tx_id", ""),
        "user_id": tx.get("user_id", ""),
        "final_action": final_action,
        "rule_ids": rule_ids,
        "score": tx.get("score"),
    }


async def _consume_loop() -> None:
    if not _HAS_AIOKAFKA:
        logger.warning("aiokafka 미설치 — Kafka consumer 비활성화")
        return

    consumer = AIOKafkaConsumer(
        TOPIC_TX_REQUEST,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset=AUTO_OFFSET_RESET,
    )
    try:
        await consumer.start()
        logger.info("Kafka consumer 시작: %s ← %s (offset=%s)",
                    CONSUMER_GROUP, TOPIC_TX_REQUEST, AUTO_OFFSET_RESET)
        async for msg in consumer:
            try:
                # W4-#3: sync 처리를 워커 스레드로 — 이벤트루프 블로킹 차단
                result = await asyncio.to_thread(_process_message, msg.value)
                await kafka_producer.send_decision(
                    result["tx_id"],
                    result["final_action"],
                    float(result.get("score") or 0),
                    result.get("rule_ids", ""),
                    user_id=result.get("user_id", ""),
                )
            except Exception as e:
                logger.error("[kafka-consumer] 메시지 처리 오류: %s | payload=%s", e, msg.value)
                # W4-#4: 처리 실패 → DLQ 폴백
                try:
                    await kafka_producer.send_dlq(msg.value, str(e))
                except Exception as dlq_err:
                    logger.error("[kafka-consumer] DLQ 발행도 실패: %s", dlq_err)
    except asyncio.CancelledError:
        logger.info("Kafka consumer 종료 요청")
        raise
    finally:
        await consumer.stop()


async def _supervisor_loop() -> None:
    """W4-#4: consumer 가 예외로 죽으면 자동 재시작.

    backoff: CONSUMER_RESTART_BACKOFF_S 초.
    stop_consumer() 가 호출되면 _stop_requested=True 로 종료.
    """
    global _stop_requested
    while not _stop_requested:
        try:
            await _consume_loop()
            if _stop_requested:
                break
            logger.warning("[kafka-supervisor] consumer가 정상 반환 — %ds 후 재시작",
                           CONSUMER_RESTART_BACKOFF_S)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[kafka-supervisor] consumer 비정상 종료: %s — %ds 후 재시작",
                         e, CONSUMER_RESTART_BACKOFF_S)
        try:
            await asyncio.sleep(CONSUMER_RESTART_BACKOFF_S)
        except asyncio.CancelledError:
            break


async def start_consumer() -> None:
    global _supervisor_task, _stop_requested
    _stop_requested = False
    _supervisor_task = asyncio.create_task(_supervisor_loop())


async def stop_consumer() -> None:
    global _supervisor_task, _stop_requested
    _stop_requested = True
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        try:
            await _supervisor_task
        except asyncio.CancelledError:
            pass
        _supervisor_task = None
