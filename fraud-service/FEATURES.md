# Fraud Service — Feature Brainstorming & Design

> 현재 구현 상태 + 두 가지 확장 방향(Option A, B)을 포함한 전체 기능 문서.
> 바뀔 것을 전제로, 나중에 구현 선택할 때 참고용.

---

## 현재 구현 상태 (Baseline)

### API 엔드포인트

| 경로 | 설명 |
|------|------|
| `POST /v1/score` | ML 모델 단건 스코어링 (XGBoost/LightGBM, joblib 번들) |
| `POST /v1/score/batch` | ML 모델 배치 스코어링 |
| `POST /v1/fraud/evaluate` | Rule + Model 통합 판단 → PASS / SOFT_REVIEW / REVIEW / BLOCK |
| `GET /v1/fraud/risk-leakage-report` | 미탐지(Leakage) 리스크 시뮬레이션 |
| `GET /admin` | 관리 대시보드 HTML |
| `GET /admin/api/status` | 모델 로드 상태 + capstone 메트릭 JSON |
| `GET /health` | 헬스체크 |

### 판단 로직

- **모델 action**: score ≥ 0.95 → BLOCK / ≥ 0.35 → REVIEW / ≥ 0.005 → SOFT_REVIEW / else → PASS
- **규칙 action**: 금액 ≥ 500만원 → BLOCK / ≥ 100만원 → REVIEW (단 1개 규칙)
- **merge**: 둘 중 더 강한 action 채택
- **Step-up Auth**: REVIEW 이상 시 push 트리거 정보 반환
- **Reason code**: feature importance × |z-score| 상위 3개 피처명

---

## Option A — Python(FastAPI) 내부 기능 확장

> fraud-service 자체를 더 풍부하게 만드는 방향.
> Spring Boot 없이도 독립 실행 가능.

---

### A-1. Rule Engine 확장

현재 금액 1개 규칙 → 다차원 규칙 체계로 확장.

#### 추가할 규칙

| Rule ID | 조건 | action |
|---------|------|--------|
| `TIME_RISK` | 새벽 02:00~05:00 AND 금액 ≥ 50만원 | REVIEW |
| `VELOCITY_FREQ` | 동일 user_id, 10분 내 3회 초과 | BLOCK |
| `SPLIT_TXN` | 10만원 이하, 5분 내 5회 연속 (쪼개기 의심) | REVIEW |
| `DEVICE_CHANGE` | 동일 세션 내 device_id 변경 | REVIEW |
| `FOREIGN_IP` | is_foreign_ip=true AND 금액 ≥ 30만원 | REVIEW |
| `AMOUNT_SPIKE` | 금액 > 사용자 평균 × 5배 | SOFT_REVIEW |
| `NEW_MERCHANT` | 처음 거래하는 merchant_id AND 금액 ≥ 20만원 | SOFT_REVIEW |

#### 설계 방향

```python
# app/services/rule_engine.py
class Rule:
    rule_id: str
    evaluate(tx: dict, profile: UserProfile | None) -> tuple[str, str]  # (action, rule_id)

class RuleEngine:
    rules: list[Rule]
    evaluate_all(tx, profile) -> list[tuple[str, str]]  # 전체 발동 규칙 목록
    get_strongest(results) -> tuple[str, str]
```

- 현재 `evaluate_amount_rule` 은 RuleEngine 안의 규칙 하나로 흡수
- `policy_merge.merge_actions` 그대로 재활용

---

### A-2. 거래 프로파일링 (인메모리, Redis 없이)

사용자별 거래 히스토리를 메모리에 누적 → 행동 기반 이상탐지 피처 생성.

#### API

| 경로 | 설명 |
|------|------|
| `POST /v1/profile/ingest` | 거래 1건을 히스토리에 누적 |
| `GET /v1/profile/{user_id}` | 집계 프로파일 반환 |
| `GET /v1/profile/{user_id}/velocity` | 최근 1분 / 5분 / 15분 거래 횟수 |
| `DELETE /v1/profile/{user_id}` | 프로파일 초기화 |

#### 집계 항목

```json
{
  "user_id": "u123",
  "tx_count": 42,
  "avg_amount": 183000,
  "max_amount": 1500000,
  "peak_hour": 14,
  "merchant_diversity": 12,
  "velocity": { "1m": 0, "5m": 1, "15m": 3 }
}
```

#### 설계 방향

```python
# app/services/profile_store.py
# 단순 dict + deque(maxlen=500) 인메모리
# 나중에 Redis로 교체 쉽도록 interface 분리
class ProfileStore:
    ingest(user_id, tx) -> None
    get_profile(user_id) -> UserProfile
    get_velocity(user_id, window_minutes) -> int
```

---

### A-3. 이상탐지 앙상블 (Isolation Forest)

XGBoost 스코어 단독 → Isolation Forest 이상 점수와 앙상블.

#### 흐름

```
features → [XGBoost] → score_ml (0~1)
         → [IsolationForest] → anomaly_score (-1~0, 낮을수록 이상)
         → ensemble_score = α * score_ml + β * normalize(anomaly_score)
```

#### API 변경

`POST /v1/score` 응답에 필드 추가:

```json
{
  "fraud_probability": 0.72,
  "anomaly_score": -0.31,
  "ensemble_score": 0.68,
  "reason_code": "V14;V4;V10"
}
```

#### 설계 방향

- `model_loader.py` 번들에 `isolation_forest` 키 추가 (없으면 XGBoost 단독)
- `app/scoring/ensemble.py` 신규 파일

---

### A-4. 시뮬레이터

개발/테스트 시 파라미터 바꿔가며 판단 결과 미리 확인.

#### API

| 경로 | 설명 |
|------|------|
| `POST /v1/simulate` | 가상 tx 파라미터 → 전체 판단 결과 미리보기 |
| `POST /v1/simulate/batch` | 시나리오 묶음 테스트 |
| `GET /v1/simulate/threshold-sweep` | BLOCK_THRESHOLD 값 범위별 BLOCK률 계산 |

#### 예시 요청/응답

```json
// POST /v1/simulate
{
  "score": 0.91,
  "amount": 300000,
  "hour": 3,
  "is_foreign_ip": true
}

// 응답
{
  "model_action": "BLOCK",
  "triggered_rules": ["TIME_RISK", "FOREIGN_IP"],
  "final_action": "BLOCK",
  "what_if": {
    "if_score_0.3": "REVIEW",
    "if_amount_50000": "SOFT_REVIEW"
  }
}
```

---

### A-5. Admin API 확장

런타임 임계값/규칙 조정 (재시작 없이).

#### API 추가

| 경로 | 설명 |
|------|------|
| `GET /admin/api/rules` | 현재 활성 규칙 목록 + 조건 |
| `PATCH /admin/api/threshold` | BLOCK/REVIEW/SOFT_REVIEW 임계값 동적 변경 |
| `POST /admin/api/rules/{rule_id}/toggle` | 규칙 활성/비활성 토글 |
| `GET /admin/api/stats` | 처리 건수, action 분포 실시간 통계 |

#### 통계 응답 예시

```json
{
  "total_evaluated": 1024,
  "action_distribution": {
    "PASS": 0.881,
    "SOFT_REVIEW": 0.072,
    "REVIEW": 0.039,
    "BLOCK": 0.008
  },
  "top_triggered_rules": ["AMOUNT_BLOCK", "VELOCITY_FREQ", "TIME_RISK"]
}
```

---

### A-6. 설명 가능성(XAI) 강화

현재 reason_code는 피처명만 반환 → 사람이 읽을 수 있는 한글 설명 추가.

#### 응답 예시

```json
{
  "reason_code": "V14;V4;V10",
  "reason_human": [
    "V14 피처가 평균 대비 3.2배 높습니다.",
    "V4 값이 정상 거래 분포 하위 1% 수준입니다.",
    "V10이 최근 5건 평균에서 크게 벗어났습니다."
  ]
}
```

---

### A-7. Step-up Auth 결과 수신

현재는 push 트리거만 → 사용자 인증 결과를 받아 최종 판단 재처리.

#### API 추가

| 경로 | 설명 |
|------|------|
| `POST /v1/auth/step-up/result` | 인증 성공/실패 수신 → tx 재판단 |

#### 흐름

```
REVIEW 판단 → push 발송 → 사용자 앱에서 승인/거절
→ POST /v1/auth/step-up/result { tx_id, approved: true }
→ approved=true  → PASS로 전환
→ approved=false → BLOCK 확정
```

---

## Option B — Spring Boot 연동 인터페이스

> fraud-service(Python)가 외부 Spring Boot 시스템과 통신하는 방향.
> Kafka, Redis, Firebase 등 인프라 연동.

---

### B-1. Kafka Consumer/Producer

거래 이벤트를 Kafka로 수신 → 스코어링 → 결과 produce.

#### 토픽 구조

| 토픽 | 방향 | 설명 |
|------|------|------|
| `txn.raw` | consume | Spring Boot에서 거래 발생 시 발행 |
| `fraud.result` | produce | FDS 판단 결과 (action, score, reason) |
| `fraud.stepup` | produce | Step-up Auth 요청 이벤트 |
| `fraud.audit` | produce | 감사 로그 |

#### 설계 방향

```python
# app/kafka/consumer.py  (aiokafka)
# app/kafka/producer.py
# main.py lifespan에서 consumer 태스크 시작
```

- REST API와 Kafka consumer 둘 다 동시 운영 (REST는 직접 호출용, Kafka는 비동기 배치용)

---

### B-2. Redis 연동

인메모리 ProfileStore → Redis로 교체.

#### 대체 대상

| 현재 (인메모리) | Redis 교체 후 |
|----------------|--------------|
| `ProfileStore` dict | `HASH` / `SORTED SET` |
| velocity 계산 deque | `ZADD` + `ZRANGEBYSCORE` (타임스탬프 기반) |
| 임계값 설정 | `GET/SET` (admin API에서 수정 가능) |
| 처리 통계 | `INCR` / `HINCR` |

#### 설계 방향

```python
# app/services/profile_store.py
class ProfileStore(Protocol):
    ingest(user_id, tx) -> None
    get_profile(user_id) -> UserProfile

class InMemoryProfileStore(ProfileStore): ...   # 현재, 로컬 개발용
class RedisProfileStore(ProfileStore): ...      # Redis 연동 시
```

config에서 `PROFILE_STORE=redis|memory` 로 전환.

---

### B-3. Firebase Push 연동

Step-up Auth 트리거 → 실제 Firebase FCM push 발송.

#### 현재

`trigger_step_up_auth()` 가 push 정보 dict만 반환 (실제 발송 안 함)

#### 추가할 것

```python
# app/services/push_service.py
async def send_push(device_token: str, title: str, body: str) -> bool:
    # firebase-admin SDK 또는 FCM REST API 호출
```

- `FraudServiceManager.trigger_step_up_auth()` 가 push_service 호출
- device_token은 요청 파라미터로 수신 or user profile에서 조회

---

### B-4. Spring Boot 연동 계약 (API Contract)

Spring Boot가 fraud-service를 호출하는 방식 정의.

#### 흐름 (동기 REST 방식)

```
[Spring Boot]
  1. 거래 발생
  2. POST /v1/score          { features: {V1..V30} }
     → { fraud_probability, reason_code }
  3. POST /v1/fraud/evaluate  { tx_id, score, amount, reason_code }
     → { final_action, step_up_auth, user_message }
  4. final_action 기반 처리:
     - PASS   → 거래 승인
     - REVIEW → step_up_auth 정보로 push 발송 후 대기
     - BLOCK  → 거래 거절 + 알림
```

#### 흐름 (비동기 Kafka 방식)

```
[Spring Boot]  →  txn.raw 토픽 publish
[fraud-service] consume → 스코어링 → fraud.result 토픽 produce
[Spring Boot]  ←  fraud.result consume → 후처리
```

---

### B-5. 인증/보안 (fraud-service 자체 보호)

현재 fraud-service는 인증 없음 → Spring Boot 내부망 전용이지만 기본 보안 추가.

| 방법 | 설명 |
|------|------|
| API Key 헤더 | `X-Fraud-Service-Key` 헤더 검증 |
| IP 화이트리스트 | Spring Boot 서버 IP만 허용 |
| JWT 검증 | Spring Boot 발급 내부 토큰 검증 (optional) |

---

## 전체 기능 목록 요약

### Option A (Python 내부)

| # | 기능 | 난이도 | 우선순위 |
|---|------|--------|--------|
| A-1 | Rule Engine 확장 (7개 규칙) | 낮음 | 높음 |
| A-2 | 거래 프로파일링 인메모리 | 낮음 | 높음 |
| A-3 | Isolation Forest 앙상블 | 중간 | 중간 |
| A-4 | 시뮬레이터 API | 낮음 | 중간 |
| A-5 | Admin API 확장 | 낮음 | 중간 |
| A-6 | XAI 한글 reason 설명 | 낮음 | 낮음 |
| A-7 | Step-up Auth 결과 수신 | 낮음 | 중간 |

### Option B (외부 연동)

| # | 기능 | 난이도 | 우선순위 |
|---|------|--------|--------|
| B-1 | Kafka Consumer/Producer | 높음 | 중간 |
| B-2 | Redis ProfileStore 교체 | 중간 | 중간 |
| B-3 | Firebase Push 실제 발송 | 중간 | 낮음 |
| B-4 | Spring Boot 연동 계약 문서화 | 낮음 | 높음 |
| B-5 | API Key 인증 | 낮음 | 낮음 |

---

## 의존 관계 (구현 순서 가이드)

```
A-2 (프로파일링)  ──→  A-1 (Rule Engine, AMOUNT_SPIKE / VELOCITY 규칙)
A-1              ──→  A-4 (시뮬레이터, triggered_rules 필드)
A-1 + A-2        ──→  A-5 (Admin stats, top_triggered_rules)
A-2              ──→  B-2 (Redis 교체, interface만 맞추면 됨)
A-7              ──→  B-3 (Firebase Push, step-up 흐름 완성)
B-4              ──→  B-1 (Kafka, 계약 확정 후 구현)
```

---

## 미결 사항 (TBD)

- [ ] Kafka 연동 여부: 비동기 필요 시기 결정
- [ ] Redis 연동 여부: 멀티 인스턴스 배포 필요 시기 결정
- [ ] Isolation Forest 모델: capstone 번들에 포함할지 별도 학습할지
- [ ] Step-up Auth 결과 수신 주체: fraud-service가 직접 받을지 Spring Boot가 중계할지
- [ ] 고객 군집화(K-Means): 군집별 임계값 분기에 쓸지 단순 피처로 쓸지
