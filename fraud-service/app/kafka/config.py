"""Kafka 설정. 환경변수 우선, 기본값은 로컬 개발용."""
import os

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_TX_REQUEST  = os.getenv("KAFKA_TOPIC_TX_REQUEST",  "fraud.transaction.requested")
TOPIC_TX_RESULT   = os.getenv("KAFKA_TOPIC_TX_RESULT",   "fraud.decision.result")

# W4-#4: Dead Letter Queue — 처리 실패 메시지가 가는 별도 토픽
TOPIC_TX_DLQ      = os.getenv("KAFKA_TOPIC_TX_DLQ",      "fraud.transaction.deadletter")

CONSUMER_GROUP    = os.getenv("KAFKA_CONSUMER_GROUP",    "fraud-service")

# W4-#3: auto_offset_reset 정책 (latest | earliest)
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
# 워치독 재시작 백오프(초)
CONSUMER_RESTART_BACKOFF_S = int(os.getenv("KAFKA_CONSUMER_RESTART_BACKOFF_S", "5"))
