"""
Kafka 결과 발행 (fraud.decision.result).

사용 예:
    await kafka_producer.send_decision(tx_id, final_action, score, rule_ids)
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

from app.kafka.config import KAFKA_BOOTSTRAP, TOPIC_TX_RESULT

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
) -> bool:
    """결과 메시지를 fraud.decision.result 토픽으로 발행. 실패 시 False 반환."""
    if _producer is None:
        return False
    payload = {
        "tx_id": tx_id,
        "final_action": final_action,
        "score": score,
        "rule_ids": rule_ids,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **(extra or {}),
    }
    try:
        await _producer.send_and_wait(TOPIC_TX_RESULT, payload)
        return True
    except Exception as e:
        logger.error("Kafka 발행 실패 tx=%s: %s", tx_id, e)
        return False
