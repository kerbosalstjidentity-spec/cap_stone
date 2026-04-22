"""
Kafka 거래 요청 수신 (fraud.transaction.requested).

Spring Boot이 발행한 메시지를 소비하여 /v1/fraud/evaluate 로직을 직접 실행.
HTTP 호출 없이 내부 함수 재활용 → 레이턴시 최소화.

메시지 스키마 (JSON):
{
  "tx_id": "...",
  "user_id": "...",
  "score": 0.85,
  "amount": 150000,
  "reason_code": "...",
  "hour": 14,
  "is_foreign_ip": false,
  "ip": "...",
  "merchant_id": "...",
  "device_id": "..."
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

from app.kafka.config import KAFKA_BOOTSTRAP, TOPIC_TX_REQUEST, CONSUMER_GROUP
from app.kafka import producer as kafka_producer

logger = logging.getLogger(__name__)

_consumer_task: asyncio.Task | None = None


def _process_message(data: dict[str, Any]) -> dict[str, Any]:
    """메시지 처리 — fraud_service 내부 로직 직접 호출."""
    # 순환 임포트 방지를 위해 함수 내부에서 임포트
    from app.services.fraud_service import FraudServiceManager
    from app.services.rule_engine import rule_engine
    from app.services.profile_store import profile_store
    from app.services.stats_collector import stats_collector

    tx = data
    profile = profile_store.get_profile(tx.get("user_id", ""))
    rule_results = rule_engine.evaluate_all(tx, profile)
    rule_action, rule_ids = rule_engine.get_strongest(rule_results)

    manager = FraudServiceManager(tx)
    final_action = manager.get_final_action()

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
        auto_offset_reset="latest",
    )
    try:
        await consumer.start()
        logger.info("Kafka consumer 시작: %s ← %s", CONSUMER_GROUP, TOPIC_TX_REQUEST)
        async for msg in consumer:
            try:
                result = _process_message(msg.value)
                await kafka_producer.send_decision(
                    result["tx_id"],
                    result["final_action"],
                    float(result.get("score") or 0),
                    result.get("rule_ids", ""),
                )
            except Exception as e:
                logger.error("메시지 처리 오류: %s | payload=%s", e, msg.value)
    except asyncio.CancelledError:
        logger.info("Kafka consumer 종료 요청")
    except Exception as e:
        logger.error("Kafka consumer 오류: %s", e)
    finally:
        await consumer.stop()


async def start_consumer() -> None:
    global _consumer_task
    _consumer_task = asyncio.create_task(_consume_loop())


async def stop_consumer() -> None:
    global _consumer_task
    if _consumer_task is not None:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None
