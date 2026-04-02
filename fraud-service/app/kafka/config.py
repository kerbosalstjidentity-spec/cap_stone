"""Kafka 설정. 환경변수 우선, 기본값은 로컬 개발용."""
import os

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_TX_REQUEST  = os.getenv("KAFKA_TOPIC_TX_REQUEST",  "fraud.transaction.requested")
TOPIC_TX_RESULT   = os.getenv("KAFKA_TOPIC_TX_RESULT",   "fraud.decision.result")
CONSUMER_GROUP    = os.getenv("KAFKA_CONSUMER_GROUP",    "fraud-service")
