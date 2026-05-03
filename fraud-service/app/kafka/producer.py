"""
Kafka 결과 발행 (fraud.decision.result) + DLQ.

사용 예:
    await kafka_producer.send_decision(tx_id, final_action, score, rule_ids)
    await kafka_producer.send_dlq(original_payload, error_str)

W4-#2: Producer 무음 실패 → 명시적 ERROR 로깅 + DLQ 폴백.
W4-#7: send_decision 은 user_id 가 있으면 partition key 로 사용 → 같은 사용자 메시지가 같은 파티션 = 순서 보장.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

try:
    from aiokafka import AIOKafkaProducer
    _HAS_AIOKAFKA = True
except ImportError:
    _HAS_AIOKAFKA = False

from app.kafka.config import KAFKA_BOOTSTRAP, TOPIC_TX_DLQ, TOPIC_TX_RESULT

logger = logging.getLogger(__name__)

_producer: Any = None  # AIOKafkaProducer | None


async def start_producer() -> None:
    global _producer
    if not _HAS_AIOKAFKA:
        logger.warning("aiokafka 미설치 — Kafka producer 비활성화")
        return
    try:
        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
        )
        await _producer.start()
        logger.info("Kafka producer 시작: %s → %s", KAFKA_BOOTSTRAP, TOPIC_TX_RESULT)
    except Exception as e:
        logger.error("Kafka producer 시작 실패: %s", e)
        _producer = None


async def stop_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def send_decision(
    tx_id: str,
    final_action: str,
    score: float,
    rule_ids: str = "",
    extra: dict | None = None,
    user_id: str = "",
) -> bool:
    """결과 메시지를 fraud.decision.result 토픽으로 발행. 실패 시 DLQ로 폴백.

    W4-#7: user_id 가 있으면 파티션 key 로 사용 → 동일 사용자 = 동일 파티션 = 순서 보장.
    W4-#2: 발행 실패 시 ERROR 로그 + DLQ 발행 시도.
    """
    payload = {
        "tx_id": tx_id,
        "final_action": final_action,
        "score": score,
        "rule_ids": rule_ids,
        "user_id": user_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **(extra or {}),
    }
    if _producer is None:
        logger.error("[kafka-producer] 미가용 상태에서 send_decision 호출 — DLQ 시도 (tx=%s)", tx_id)
        return await send_dlq(payload, "producer-unavailable")

    partition_key = user_id or tx_id  # 사용자 없으면 tx_id로라도 일관성 유지
    try:
        await _producer.send_and_wait(TOPIC_TX_RESULT, value=payload, key=partition_key)
        return True
    except Exception as e:
        logger.error("[kafka-producer] 발행 실패 tx=%s: %s — DLQ 폴백", tx_id, e)
        await send_dlq(payload, str(e))
        return False


async def send_dlq(original_payload: dict, error: str) -> bool:
    """W4-#4: 처리 실패 메시지를 DLQ 토픽으로 보낸다."""
    if _producer is None:
        return False
    dlq_msg = {
        "original": original_payload,
        "error": error,
        "failed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    try:
        await _producer.send_and_wait(TOPIC_TX_DLQ, value=dlq_msg)
        logger.warning("[kafka-dlq] enqueued tx=%s err=%s",
                       original_payload.get("tx_id", "?"), error)
        return True
    except Exception as e:
        logger.error("[kafka-dlq] DLQ 발행도 실패: %s", e)
        return False
