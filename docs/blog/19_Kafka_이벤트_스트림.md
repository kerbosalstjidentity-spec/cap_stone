# #19 Kafka 이벤트 스트림 — 코드 골격만 존재하고 실제로는 도입되지 않은 비동기 채널

## ① 개요 (실태 먼저)

`app/kafka/` 패키지는 fraud-service와 backend를 비동기 이벤트로 연결하기 위한 **설계 골격**이다. 그러나 코드를 따라가다 보면 실제 운영 환경에는 **연결되어 있지 않다는 사실이 명확히 드러난다**:

- `fraud-service/requirements.txt` 에 `aiokafka` 패키지가 **포함되어 있지 않다** → `try: from aiokafka import …` 가 항상 `ImportError`로 떨어져 `_HAS_AIOKAFKA = False`
- `docker-compose.yml` 에 **Kafka 브로커 서비스 정의가 없다** (postgres, redis, fraud-service, backend, frontend만 존재)
- backend (Python FastAPI) 코드에 Kafka 키워드가 **0건** — consumer.py 주석은 "Spring Boot이 발행한다"고 쓰여 있지만 실제 backend는 Spring이 아니다
- backend는 `FRAUD_SERVICE_URL=http://fraud-service:8010` 환경변수로 fraud-service를 **HTTP 직접 호출**한다

따라서 부팅 시 `start_producer()`/`start_consumer()` 양쪽 모두 "aiokafka 미설치 — 비활성화" WARNING만 찍고 즉시 종료된다. 이 글에서는 **"미래에 Kafka를 도입한다면 어떤 모양일 것인가"의 청사진**으로 코드를 분석하되, 현재 상태가 추론 시점에 살아있다고 오해하지 않도록 미연결 부분을 명시한다.

---

## ② 시스템 구성

```
Spring Boot
  │
  │  produce → "fraud.transaction.requested"
  │  { tx_id, user_id, score, amount, hour,
  │    is_foreign_ip, ip, merchant_id, device_id }
  ▼
┌──────────────────────────────────────────────┐
│  AIOKafkaConsumer (_consume_loop)            │
│  auto_offset_reset = "latest"                │
│  group_id = "fraud-service"                  │
│                                              │
│  msg.value → _process_message()             │
│    ├─ profile_store.get_profile(user_id)    │
│    ├─ rule_engine.evaluate_all(tx, profile) │
│    ├─ rule_engine.get_strongest(results)    │
│    └─ FraudServiceManager.get_final_action()│
│                                              │
│  → send_decision(tx_id, action, score, …)   │
└──────────────────┬───────────────────────────┘
                   │
                   │  produce → "fraud.decision.result"
                   │  { tx_id, final_action, score,
                   │    rule_ids, timestamp }
                   ▼
           Spring Boot / 알림 서비스

┌──────────────────────────────────────────────┐
│  AIOKafkaProducer (start_producer)           │
│  value_serializer: JSON → bytes              │
│  send_and_wait() — ACK 확인 후 반환          │
└──────────────────────────────────────────────┘

FastAPI lifespan:
  startup  → start_producer() → start_consumer()
  shutdown → stop_consumer()  → stop_producer()
```

| 파일 | 역할 |
|---|---|
| `app/kafka/config.py` | 환경변수 기반 브로커 주소·토픽명·컨슈머 그룹 |
| `app/kafka/producer.py` | `AIOKafkaProducer` 래퍼 + `send_decision()` |
| `app/kafka/consumer.py` | `AIOKafkaConsumer` 루프 + `_process_message()` |
| `app/main.py:21-26` | lifespan 훅으로 producer → consumer 순 시작 |

**토픽 구성:**

| 토픽 | 방향 | 발행자 | 구독자 |
|---|---|---|---|
| `fraud.transaction.requested` | Spring Boot → fraud-service | Spring Boot | fraud-service consumer |
| `fraud.decision.result` | fraud-service → 외부 | fraud-service producer | Spring Boot / 알림 서비스 |

---

## ③ 동작 흐름

```
1. FastAPI 앱 시작 → lifespan 진입
2. start_producer(): AIOKafkaProducer 생성 & .start()
3. start_consumer(): asyncio.create_task(_consume_loop()) 백그라운드 등록
4. _consume_loop():
   4a. AIOKafkaConsumer 생성 & .start()
   4b. async for msg in consumer: 무한 이벤트 루프 진입
5. Spring Boot가 fraud.transaction.requested에 메시지 발행
6. _consume_loop가 msg 수신
7. _process_message(msg.value) 호출 (동기 함수 — asyncio 이벤트루프에서 직접 실행)
   7a. profile_store.get_profile(user_id)
   7b. rule_engine.evaluate_all(tx, profile) + get_strongest()
   7c. FraudServiceManager(tx).get_final_action()
   7d. stats_collector.record(...)
8. kafka_producer.send_decision() 호출 → fraud.decision.result 발행
9. 처리 오류 시 logger.error 후 다음 메시지로 계속 진행 (skip)

[종료 흐름]
1. lifespan 종료 → stop_consumer() → _consumer_task.cancel()
2. asyncio.CancelledError 잡아 consumer.stop() 보장
3. stop_producer() → _producer.stop()
```

---

## ④ 핵심 코드 분석

### 4-1. aiokafka 선택적 임포트 — graceful degradation

```python
# producer.py:14-18 / consumer.py:29-33
try:
    from aiokafka import AIOKafkaProducer
    _HAS_AIOKAFKA = True
except ImportError:
    _HAS_AIOKAFKA = False
```

[producer.py:14](fraud-service/app/kafka/producer.py:14)

`aiokafka`가 설치되지 않아도 앱이 시작된다. `start_producer()`에서 `_HAS_AIOKAFKA`가 False면 WARNING 로그만 남기고 `_producer = None`으로 유지된다. `send_decision()`은 `_producer is None`이면 `False`만 반환한다. Kafka 없는 개발 환경에서 전체 fraud-service를 그대로 실행할 수 있는 선택적 의존성 패턴이다.

### 4-2. 메시지 처리 — HTTP 없이 내부 로직 직접 호출

```python
# consumer.py:42-72
def _process_message(data: dict[str, Any]) -> dict[str, Any]:
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

    stats_collector.record(...)
    return {"tx_id": ..., "final_action": final_action, ...}
```

[consumer.py:42](fraud-service/app/kafka/consumer.py:42)

`_process_message`는 **동기 함수**다. HTTP 라우터와 완전히 동일한 fraud_service/rule_engine/profile_store 스택을 직접 호출한다. HTTP 라운드트립 없이 같은 프로세스 내에서 평가가 완결된다. 순환 임포트 방지를 위해 import를 함수 내부에 배치한 점도 눈에 띈다.

### 4-3. 프로듀서 — send_and_wait 와 직렬화

```python
# producer.py:33-41
_producer = AIOKafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode(),
)

# producer.py:70-71
await _producer.send_and_wait(TOPIC_TX_RESULT, payload)
return True
```

[producer.py:33](fraud-service/app/kafka/producer.py:33)

`send_and_wait`는 브로커가 메시지를 수신 확인(ACK)할 때까지 await한다. fire-and-forget의 `send()`와 달리, 발행 실패를 즉시 알 수 있다. 단, 브로커가 느리면 `_consume_loop`의 처리 속도가 그만큼 늦어진다.

### 4-4. 컨슈머 재시작 전략 — Task 기반 백그라운드

```python
# consumer.py:109-122
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
```

[consumer.py:109](fraud-service/app/kafka/consumer.py:109)

`asyncio.create_task`로 컨슈머 루프를 이벤트루프에 등록하고 핸들(`_consumer_task`)을 보관한다. shutdown 시 `.cancel()` → `CancelledError` 잡기 → `consumer.stop()` 순서로 graceful 종료를 보장한다. finally 블록 덕분에 CancelledError가 발생해도 `consumer.stop()`은 반드시 호출된다.

### 4-5. lifespan 순서 — producer 먼저, consumer 나중

```python
# main.py:21-26
@asynccontextmanager
async def lifespan(app: FastAPI):
    await kafka_producer.start_producer()   # 1순위
    await kafka_consumer.start_consumer()   # 2순위
    yield
    await kafka_consumer.stop_consumer()    # 1순위
    await kafka_producer.stop_producer()    # 2순위
```

[main.py:21](fraud-service/app/main.py:21)

producer를 먼저 시작하는 이유: consumer가 메시지를 받아 `send_decision()`을 호출할 때 producer가 이미 준비되어 있어야 한다. 종료는 반대 순서 — consumer를 먼저 멈춰 새 메시지를 받지 않고, 이미 처리 중인 `send_decision()` 호출이 끝난 뒤 producer를 종료한다.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **`auto_offset_reset="latest"` — 재시작 시 메시지 유실**: 컨슈머 그룹 오프셋이 없을 때(최초 시작, 그룹 ID 변경) `"latest"`는 해당 시점 이후 메시지만 소비한다. 서비스가 재시작되는 동안 들어온 메시지는 Kafka에 쌓여있지만 소비되지 않는다. `"earliest"`로 바꾸거나 Dead Letter Queue를 두면 재시작 갭을 복구할 수 있다. 금융 거래 누락은 `"latest"`를 쓰기 전에 명시적으로 수용 가능한 SLA인지 확인해야 한다. (✅ ROADMAP W4-#1,#4 — `KAFKA_AUTO_OFFSET_RESET` env, DLQ 토픽 `fraud.transaction.deadletter` 추가)

- **_process_message가 동기 함수 — 이벤트루프 블로킹 위험**: `_consume_loop`는 async 컨텍스트에서 동기 함수 `_process_message()`를 직접 호출한다. XGBoost 추론이나 rule_engine 순회가 수십ms 걸리면 그 시간 동안 이벤트루프 전체가 블로킹된다. HTTP 요청도 같은 이벤트루프를 공유하므로, 고부하 시 REST API 응답 지연으로 이어진다. `await asyncio.to_thread(_process_message, msg.value)`로 감싸면 스레드풀에서 실행되어 이벤트루프를 해방한다. (✅ ROADMAP W4-#3 — `await asyncio.to_thread(...)` 적용)

- **오류 시 메시지 skip — 사기 탐지 누락**: `_consume_loop` catch 블록은 `logger.error()` 후 다음 메시지로 넘어간다. 메시지 파싱 오류나 모델 예외가 발생하면 해당 거래는 **탐지되지 않고 조용히 무시**된다. 금융 도메인에서 이는 큰 리스크다. 처리 실패 메시지를 `fraud.transaction.deadletter` 토픽으로 재발행하고 별도 알람을 울려야 운영팀이 놓친 거래를 복구할 수 있다. (✅ ROADMAP W4-#4 — 처리 실패 시 `kafka_producer.send_dlq()` 자동 호출로 DLQ 재발행)

- **컨슈머 루프 크래시 후 자동 재시작 없음**: `_consume_loop`에서 예상치 못한 예외가 발생하면 `finally` 블록에서 `consumer.stop()`이 호출된 뒤 Task가 끝난다. `_consumer_task`는 완료 상태가 되지만 이를 감지해 재시작하는 코드가 없다. 서비스는 살아있는데 Kafka 소비는 멈춘 "zombie" 상태가 된다. `/health` 엔드포인트에서 `_consumer_task.done()` 여부를 체크하거나, exponential backoff로 재시작하는 supervisor loop가 필요하다. (✅ ROADMAP W4-#4 — `_supervisor_loop()` backoff 5s 자동 재시작 + `_stop_requested` 플래그로 정상 종료 분리)

- **send_decision 실패가 평가 결과를 삭제한다**: `send_decision()`이 `False`를 반환해도 `_consume_loop`는 아무 조치 없이 다음 메시지로 간다. 평가는 완료됐지만 결과가 발행되지 않은 거래가 생긴다. Spring Boot 입장에서는 해당 거래의 판정 결과를 영원히 받지 못한다. 발행 실패 시 재시도 큐 또는 fallback HTTP 콜백이 필요하다. (✅ ROADMAP W4-#2,#7 — send_decision 발행 실패 시 ERROR 로그 + DLQ 자동 폴백, `key=user_id` 파티셔닝으로 동일 사용자 순서 보장)

---

### 예상 질문 & 답변 (발표 Q&A 대비)

**Q1. Kafka가 미도입인데 왜 코드가 있나요?**
> 향후 backend↔fraud-service 비동기 채널 청사진. 현재는 `aiokafka` 미설치 + 브로커 부재로 부팅 시 비활성화 WARNING만 찍고 종료. 실제 운영 경로는 HTTP REST.

**Q2. Kafka 도입의 실익은?**
> ① backend 응답 지연을 fraud-service 처리 시간에서 분리, ② 거래 이벤트 fan-out(다수 컨슈머), ③ 장애 격리. 다만 인프라 복잡도 증가가 트레이드오프라 우선순위 후순위.

---

## ⑥ 한 줄 정리

`aiokafka` 기반 컨슈머-프로듀서 쌍으로 backend와의 HTTP 의존성을 끊으려는 비동기 청사진 — 다만 현재는 `aiokafka` 의존성·Kafka 브로커·발행자 측 코드가 모두 부재해 부팅 시 비활성화 상태로만 머무는 **미도입 골격**이며, 실제 운영 경로는 backend → fraud-service 의 HTTP 직접 호출이다.
