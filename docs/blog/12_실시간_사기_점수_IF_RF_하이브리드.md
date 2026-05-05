# #12 실시간 사기 점수 — Isolation Forest + 부스팅 하이브리드 스코어링

## ① 개요

PayWise의 fraud-service는 거래 한 건당 **수십 ms 안에 사기 확률을 계산하고 PASS/SOFT_REVIEW/REVIEW/BLOCK 4단계로 분류**한다. 핵심 설계는 지도학습(부스팅 트리)과 비지도학습(Isolation Forest)을 가중 평균으로 결합하는 하이브리드 앙상블이며, 여기에 규칙 엔진의 결과를 병합하여 최종 조치를 정한다. "내 모델이 본 적 없는 패턴"을 IF가 잡고, "학습된 사기 패턴"을 부스팅 모델이 잡는 상호 보완 구조다.

> ⚠️ 진행 현황 문서에는 "IF + RF" 라고 표기되어 있지만, 실제 [ensemble.py](fraud-service/app/scoring/ensemble.py:1) 의 docstring과 호출부는 **XGBoost** 를 사용한다. 본 글에서는 "부스팅 모델"로 일반화하여 서술하되, 코드는 그대로 인용한다.

---

## ② 시스템 구성

```
[클라이언트/백엔드]
       │
       ▼
┌──────────────────────────────────────────────┐
│  POST /v1/score  (routes_score.py)            │
│   ├─ load_model_bundle()  → joblib pkl        │
│   ├─ Imputer → XGBoost.predict_proba()        │
│   ├─ ensemble_score()  ─ IF.score_samples()   │
│   └─ reason_codes  (importance × |z|)         │
│      ↓ fraud_probability, reason_code         │
└──────────────────────────────────────────────┘
       │ (점수만 별도 호출 가능)
       ▼
┌──────────────────────────────────────────────┐
│  POST /v1/evaluate  (routes_fraud.py)         │
│   ├─ FraudServiceManager(score, amount, …)    │
│   │    ├─ get_model_action()  임계값 4단계   │
│   │    ├─ get_rule_action()   rule_engine    │
│   │    └─ get_final_action()  policy_merge   │
│   ├─ analyze_signals  (Layer 1 행동 시그널)  │
│   ├─ stats_collector / audit_logger           │
│   ├─ blockchain_audit.append                  │
│   └─ trigger_step_up_auth (FCM 푸시)          │
└──────────────────────────────────────────────┘
       │
       ▼
   사용자 메시지 / Step-up 인증 / 차단
```

| 파일 | 역할 |
|---|---|
| `app/scoring/ensemble.py` | XGBoost + Isolation Forest 가중 평균 |
| `app/scoring/reason_codes.py` | 상위 기여 특성 추출 + 한글 설명 |
| `app/api/routes_score.py` | 점수만 반환하는 단건/배치 API |
| `app/api/routes_fraud.py` | 점수 + 룰 + 후처리 통합 평가 API |
| `app/services/fraud_service.py` | 임계값·메시지·Step-up 트리거 |
| `app/services/policy_merge.py` | 모델 vs 규칙 병합 (max-rank) |

---

## ③ 동작 흐름

```
1. 클라이언트가 트랜잭션 V1..V30 특성을 /v1/score 로 전송
2. load_model_bundle() — joblib 번들에서 (pipeline, feature_names, isolation_forest) 로드
3. Imputer 결측치 보정 → XGBoost.predict_proba()[:, 1] = xgb_proba
4. IsolationForest.score_samples(X)[0] → _normalize_anomaly() 로 [0,1] 매핑 = anomaly
5. combined = 0.7 * xgb_proba + 0.3 * anomaly  (ALPHA=0.7, BETA=0.3)
6. importances * (1 + |z|) 정렬 → top-3 reason_code 생성
7. (별도 호출) /v1/evaluate 가 combined 점수와 amount/IP/시각 등을 받아
   FraudServiceManager 로 model_action / rule_action / final_action 결정
8. final_action 이 REVIEW 이상이면 FCM 푸시 발송 (Step-up 인증)
9. stats_collector + audit_logger + blockchain_audit.append (3중 기록)
10. 사용자에게 status + message 반환, Step-up 결과 도착 시 final_action 갱신
```

---

## ④ 핵심 코드 분석

### 4-1. Isolation Forest 점수 정규화

IF 의 `score_samples()` 는 음수를 반환하며 **낮을수록 이상**이다 (대략 -0.5 ~ -0.05 범위). 이걸 부스팅 확률(0~1)과 가중 평균하려면 같은 스케일로 맞춰야 한다.

```python
# ensemble.py:17-26
def _normalize_anomaly(raw_score: float) -> float:
    LOW, HIGH = -0.5, -0.05
    clipped = max(LOW, min(HIGH, raw_score))
    normalized = (clipped - HIGH) / (LOW - HIGH)   # 0(정상)~1(이상)
    return float(normalized)
```

[ensemble.py:17](fraud-service/app/scoring/ensemble.py:17)

선형 클리핑 + 단순 min-max 변환이다. `LOW`보다 낮은 극단치는 1.0, `HIGH`보다 높은 정상값은 0.0으로 잘린다. 분포가 안정적이지 않으면 `LOW/HIGH` 상수가 데이터 드리프트에 취약하다는 단점이 있지만, 운영팀이 점수의 의미를 이해하기 쉽다는 장점이 있다.

### 4-2. 가중 평균 앙상블 — α=0.7, β=0.3

```python
# ensemble.py:12-14, 29-48
ALPHA = 0.7   # XGBoost 비중
BETA  = 0.3   # Isolation Forest 비중

def ensemble_score(xgb_proba, bundle, X):
    iso = bundle.get("isolation_forest")
    if iso is None:
        return xgb_proba, None              # IF 없으면 XGB 단독

    try:
        raw = float(iso.score_samples(X)[0])
        anomaly = _normalize_anomaly(raw)
        combined = ALPHA * xgb_proba + BETA * anomaly
        return round(min(combined, 1.0), 6), round(raw, 6)
    except Exception:
        return xgb_proba, None              # 실패 시 fallback
```

[ensemble.py:29](fraud-service/app/scoring/ensemble.py:29)

**핵심 설계 의도**:
- `iso is None` 또는 예외 발생 시 XGBoost 단독 점수로 자동 폴백 — 모델 번들 호환성 문제로 IF가 빠져도 서비스가 죽지 않는다.
- `min(combined, 1.0)` 로 상한을 명시 — 부동소수 오차로 1.0001 같은 값이 나와도 안전하다.
- 가중치가 모듈 상수로 하드코딩 — 주석에 "나중에 SYSTEM_CONFIG 또는 .env로 빼도 됨" 이라고 향후 작업이 표시되어 있다.

### 4-3. 점수 API의 전체 파이프라인

```python
# routes_score.py:44-77
@router.post("/score")
def score(req: ScoreRequest):
    bundle = load_model_bundle()
    if bundle is None:
        return {"fraud_probability": None, "detail": "MODEL_PATH 미설정 …"}
    pipe, names, importances = meta

    X = features_dict_to_matrix(req.features, names)
    X_t = pipe.named_steps["imputer"].transform(X)
    proba = pipe.named_steps["clf"].predict_proba(X_t)[:, 1]

    xgb_proba = float(np.asarray(proba).ravel()[0])
    final_proba, anomaly_score = ensemble_score(xgb_proba, bundle, X_t)

    reason_code = ""
    reason_human: list[str] = []
    if importances is not None:
        reason_code = single_reason(X_t[0], names, importances)
        reason_human = reason_code_to_human(X_t[0], names, importances)

    return {
        "fraud_probability": final_proba,    # 앙상블 결과
        "xgb_probability": xgb_proba,        # XGB 순수 확률
        "anomaly_score": anomaly_score,      # IF 원본 (디버그용)
        "reason_code": reason_code,
        "reason_human": reason_human,
        "feature_count": len(names),
    }
```

[routes_score.py:44](fraud-service/app/api/routes_score.py:44)

응답에서 `xgb_probability` 와 `anomaly_score` 를 분리해서 노출하는 것이 인상적이다. 앙상블 결과만 반환하면 운영팀이 "두 모델 중 어느 쪽이 발화했는가"를 추적할 수 없는데, 두 점수를 모두 반환하면 reason analysis 가 가능하다.

### 4-4. Reason Code — 중요도 × z-score

```python
# reason_codes.py:8-30
def top_feature_reasons(X, feature_names, importances, *, top_k=3):
    mu  = X.mean(axis=0)
    std = np.maximum(X.std(axis=0), 1e-9)
    z   = np.abs((X - mu) / std)
    imp = np.asarray(importances, dtype=float)
    out: list[str] = []
    for i in range(X.shape[0]):
        score = imp * (1.0 + z[i])
        idx   = np.argsort(-score)[:top_k]
        out.append(";".join(feature_names[j] for j in idx))
    return out
```

[reason_codes.py:8](fraud-service/app/scoring/reason_codes.py:8)

핵심 공식은 `score = importance * (1 + |z|)`. 모델이 "전반적으로 중요하다"고 본 특성(importance)과, 이번 거래에서 "유달리 비정상적인" 특성(z-score)을 곱해 그 거래만의 reason 을 뽑는다.

다만 **단건 입력일 때**(`X.shape[0] == 1`) 자기 자신이 곧 평균이므로 `z = 0` 이 되고, 결과는 순수 importance 순위와 동일해진다. 이는 코드 주석에 명시되어 있는 의도된 동작인데, 실제로는 단건 호출이 더 흔하므로 `/score/batch` 를 통해 배치 호출할 때만 z-score 가 의미 있게 작동한다.

### 4-5. 4단계 임계값 — 모델 액션

```python
# fraud_service.py:8-17, 27-34
SYSTEM_CONFIG = {
    "BLOCK_THRESHOLD":  0.95,   # ≥0.95 → BLOCK
    "REVIEW_THRESHOLD": 0.35,
    "P99_THRESHOLD":    0.005,  # 잠재 위험군 기준
    "PASS_RATE":        0.998,
    "MISS_RATE":        0.334,  # 1 - holdout_recall(0.666)
    "AMOUNT_BLOCK_THRESHOLD":  5_000_000,
    "AMOUNT_REVIEW_THRESHOLD": 1_000_000,
}

def get_model_action(self) -> str:
    if self.score >= SYSTEM_CONFIG["BLOCK_THRESHOLD"]:
        return "BLOCK"
    if self.score >= SYSTEM_CONFIG["REVIEW_THRESHOLD"]:
        return "REVIEW"
    if self.score >= SYSTEM_CONFIG["P99_THRESHOLD"]:
        return "SOFT_REVIEW"
    return "PASS"
```

[fraud_service.py:27](fraud-service/app/services/fraud_service.py:27)

임계값 분포에서 흥미로운 점:
- **0.95 (BLOCK)** 와 **0.35 (REVIEW)** 사이의 간격이 매우 넓다 — 모델 점수가 0.4~0.94 인 거래는 모두 REVIEW 로 떨어져 사람이 검토해야 한다. 이는 보수적인 운영 정책으로, false negative 비용이 false positive 비용보다 크다는 가정을 내포한다.
- **P99_THRESHOLD = 0.005** — 0.5% 라는 매우 낮은 값. 사실상 0이 아닌 거의 모든 거래가 최소 SOFT_REVIEW 로 분류돼 모니터링 큐에 들어간다. 이름이 "P99"인 이유는 정상 거래의 99%가 이 값 미만이라는 가정에서 온 것으로 보인다.

### 4-6. 모델 vs 규칙 — max-rank 병합

```python
# policy_merge.py:5-13
ACTION_RANK     = {"PASS": 0, "SOFT_REVIEW": 1, "REVIEW": 2, "BLOCK": 3}
RANK_TO_ACTION  = {0: "PASS", 1: "SOFT_REVIEW", 2: "REVIEW", 3: "BLOCK"}

def merge_actions(rule_action: str, model_action: str) -> str:
    r = ACTION_RANK.get(rule_action, 0)
    m = ACTION_RANK.get(model_action, 0)
    return RANK_TO_ACTION[max(r, m)]
```

[policy_merge.py:5](fraud-service/app/services/policy_merge.py:5)

```python
# fraud_service.py:48-52
def get_final_action(self) -> str:
    model_action = self.get_model_action()
    rule_action, _ = self.get_rule_action()
    return merge_actions(rule_action, model_action)
```

매우 단순하지만 강력한 정책이다. 두 시스템 중 **하나라도** 강한 신호를 보내면 그쪽을 따른다. 결과적으로:
- 모델이 안전(PASS)이라 해도 룰이 BLOCK 이면 차단 — 모델이 학습하지 못한 신종 사기를 룰이 잡는 시나리오
- 모델이 BLOCK 이라도 룰이 PASS 면 BLOCK 유지 — 합법적 화이트리스트는 룰 단계에서 미리 PASS 처리

이 비대칭 안전망 덕분에, 모델/룰 어느 한쪽이 실패해도 다른 쪽이 fallback 해준다.

### 4-7. Step-up 인증 트리거 + 비동기 결과 반영

```python
# fraud_service.py:91-110
def trigger_step_up_auth(self) -> dict:
    action = self.get_final_action()
    fcm_token = self.tx.get("fcm_token", "")

    if action == "BLOCK":
        payload = build_step_up_payload(tx_id, self.amount, "BLOCK_ALERT")
        if fcm_token:
            send_sync(fcm_token, payload["title"], payload["body"], payload["data"])
        return {"push_sent": bool(fcm_token), "type": "BLOCK_ALERT", **payload}

    if action in ("REVIEW", "SOFT_REVIEW"):
        payload = build_step_up_payload(tx_id, self.amount, "STEP_UP_AUTH")
        if fcm_token:
            send_sync(fcm_token, payload["title"], payload["body"], payload["data"])
        return {"push_sent": bool(fcm_token), "type": "STEP_UP_AUTH", **payload}

    return {"push_sent": False}
```

[fraud_service.py:91](fraud-service/app/services/fraud_service.py:91)

```python
# routes_fraud.py:75-83  -- evaluate 시점에 대기열에 등록
if step_up.get("push_sent") and final_action in ("REVIEW", "SOFT_REVIEW"):
    with _stepup_lock:
        _stepup_store[tx_data["tx_id"]] = {
            "score": tx_data.get("score"),
            "amount": tx_data.get("amount"),
            "reason_code": tx_data.get("reason_code", ""),
            "pre_action": final_action,
            "status": "pending",
        }
```

[routes_fraud.py:75](fraud-service/app/api/routes_fraud.py:75)

```python
# routes_fraud.py:124-156 -- 사용자 응답 도착 시 최종 action 결정
@router.post("/auth/step-up/result")
def step_up_result(req: StepUpResultRequest):
    if req.approved:
        final_action = "PASS"     # 본인 확인 성공 → 통과
    else:
        final_action = "BLOCK"    # 본인 거절 → 차단
```

[routes_fraud.py:124](fraud-service/app/api/routes_fraud.py:124)

비동기 흐름의 묘미는 **`final_action` 이 두 번 결정된다**는 점이다. 첫 결정은 모델+룰의 합의(`REVIEW` 등)이고, 두 번째는 사용자의 push 응답에 따라 PASS 또는 BLOCK 으로 확정된다. `_stepup_store` 는 메모리 dict + threading.Lock 으로 보호되어 단일 인스턴스에서만 동작 — 멀티 인스턴스 배포 시 Redis 같은 공유 저장소가 필요하다.

### 4-8. 평가 1회당 4중 기록

```python
# routes_fraud.py:42-73
def _evaluate_one(tx_data: dict) -> dict[str, Any]:
    signal_result = analyze_signals(tx_data.get("signals"))     # ① Layer 1
    manager = FraudServiceManager(tx_data)
    model_action  = manager.get_model_action()
    rule_action, rule_id = manager.get_rule_action()
    final_action  = manager.get_final_action()
    step_up       = manager.trigger_step_up_auth()              # ② FCM

    stats_collector.record(tx_id, final_action, triggered, score, amount)  # ③ 통계
    audit_logger.write(tx_id=…, final_action=…, …)                         # ④ 감사 로그
    audit_chain.append(transaction_id=…, action=…, …)                      # ⑤ 블록체인 감사
```

[routes_fraud.py:42](fraud-service/app/api/routes_fraud.py:42)

평가 한 건당 행동 시그널 분석 → push 발송 → 통계 수집 → 감사 로그 → 블록체인 감사가 **순차적으로** 동기 실행된다. 빠른 응답 시간이 중요한 결제 흐름에선 부담스러워 보일 수 있지만, 각 작업이 인메모리 또는 비동기 큐 enqueue 수준이라 ms 단위로 끝난다. 향후 Kafka 로 옮기면 더 깔끔해질 영역이다.

---

## ⑤ 설계 포인트 / 트러블슈팅 거리

- **이름과 구현의 불일치 (RF vs XGBoost)**: 진행 현황 메타데이터에는 "Random Forest" 로 표기되어 있지만 실제 [ensemble.py:1-2](fraud-service/app/scoring/ensemble.py:1) docstring은 "Isolation Forest + XGBoost" 로 명시되어 있다. 모델 학습 파이프라인에서 RF를 평가용으로 쓰고 XGB를 프로덕션에 채택했을 가능성이 있는데, 문서 일관성 차원에서 정리가 필요하다.

- **앙상블 가중치 ALPHA/BETA 하드코딩**: 0.7/0.3 비율이 모듈 상수로 박혀 있다. 새 데이터 분포에서 IF 의 기여도가 더 커야 할 경우 코드 수정 → 배포가 필요하므로, [ensemble.py:13](fraud-service/app/scoring/ensemble.py:13) 주석에 표기된 대로 `.env` 또는 `SYSTEM_CONFIG` 로 빼는 작업이 우선순위 높다. A/B 테스트 (#18) 와 결합하면 가중치 자동 튜닝까지 가능하다.

- **IF 정규화 상수의 데이터 드리프트 취약성**: `_normalize_anomaly` 의 `LOW=-0.5, HIGH=-0.05` 는 학습 시점의 score 분포를 가정한다. 시간이 지나 거래 분포가 바뀌면 IF 점수의 실제 범위도 바뀌어 클리핑이 모든 점수를 0 또는 1로 몰아넣을 수 있다. 학습마다 quantile (예: 5th/95th) 기반으로 상수를 재계산해 번들에 함께 저장하는 것이 안전하다.

- **단건 호출 시 reason_code 의 z-score 무력화**: `top_feature_reasons` 는 입력 행렬 내부 평균/표준편차를 사용하므로 1행 입력에선 항상 z=0 이 된다. 결과적으로 reason 은 단순 importance top-3 가 되어 거래마다 동일한 reason 이 나올 위험이 있다. 학습 데이터의 통계 (mu, std) 를 번들에 저장해두고 단건 호출 시 그것을 사용해야 거래별 차별화가 생긴다.

- **`_stepup_store` 가 인메모리 dict**: [routes_fraud.py:18](fraud-service/app/api/routes_fraud.py:18) 에서 `_stepup_store: dict[str, dict] = {}` + `threading.Lock` 으로 동기화한다. 단일 워커/단일 인스턴스에서는 동작하지만, FastAPI 를 Gunicorn `--workers 4` 또는 K8s replica 로 띄우면 워커마다 별도 dict 가 생겨 push 결과가 다른 워커로 라우팅되면 404 가 발생한다. Redis hash + TTL 로 옮기는 것이 표준 해법. (✅ ROADMAP W2-#2 — `app.services.stepup_store` Redis hash + 30분 TTL, 미가용 시 in-memory 폴백)

- **policy_merge 의 max-rank 단순함이 강점이자 약점**: 두 시스템 중 강한 쪽을 따르는 정책은 직관적이지만, 룰이 false positive 가 많은 경우 모델이 PASS 라 판단해도 룰 BLOCK 이 우선되어 사용자 경험이 손상된다. 룰별 정확도 통계 + 모델 신뢰도를 함께 보는 가중 정책으로 진화 여지가 있다.

- **순차적 4중 기록의 응답 지연**: stats_collector, audit_logger, blockchain_audit, FCM 발송이 모두 `_evaluate_one` 내부에서 동기 호출된다. 각각 ms 단위라도 누적되면 P99 지연이 늘어난다. push 와 audit_chain 은 백그라운드 태스크로 분리해 fire-and-forget 처리하는 것이 자연스럽다.

---

### 도메인 확장 로드맵 — "이상 거래 스크리닝"에서 "FDS"로

본 시스템의 학습 데이터([Kaggle creditcard.csv](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud), V1~V30 PCA 익명 카드결제)와 룰 엔진(금액·시간·빈도 기반 통계적 이상치)은 **금융권에서 통상 의미하는 FDS** — 보이스피싱·머니뮬·계정탈취·자금세탁 같은 도메인 사기 — 와는 갭이 있다. "사기 탐지"라기보다 **행동 이상 + 룰 기반 결제 리스크 스크리닝**에 가깝다는 점을 정직하게 인정하고, 갭을 메우는 4개 확장 트랙을 후속 작업으로 정의한다.

#### Track 1. 학습 데이터셋 도메인 교체 (PaySim)
- **결손**: V1~V30 PCA 익명 피처는 카드결제 분포 학습용. 송금자↔수취자 관계, 잔액 변화, 거래 유형(`type`) 정보가 없음
- **교체 대상**: [Kaggle PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1) — 모바일 머니 시뮬레이션 데이터셋. `nameOrig`/`nameDest` (송금 그래프), `oldbalanceOrg`/`newbalanceDest` (잔액 변화), `type ∈ {CASH_OUT, TRANSFER, PAYMENT, CASH_IN, DEBIT}`, `isFraud` 도메인 라벨 포함
- **코드 변경 위치**: [`fds-research/train_export_rf.py`](fds-research/train_export_rf.py) 데이터 로더 + feature 컬럼, [`fraud-service/app/scoring/features.py`](fraud-service/app/scoring/features.py) 입력 스키마, [`ensemble.py`](fraud-service/app/scoring/ensemble.py) 의 `_normalize_anomaly` 상수 재튜닝
- **의존성**: Track 3·4의 전제 조건. 이게 먼저 들어가야 송금 사기·그래프 피처가 의미를 가짐
- **작업량**: 1주
- (✅ ROADMAP W5.5-#2 — `fds-research/data/paysim.csv` 배치(6.36M행, 사기율 0.129%) + `scripts/paysim/load.py` 표준 로더 + `make paysim-download` 타겟 + `.gitignore` 등록. 학습 스크립트는 W5.5-#3 에서 합류)
- (✅ ROADMAP W5.5-#3 — `train_paysim.py` IF+RF 하이브리드 학습 스크립트 + `model_bundle_paysim.joblib` (TRANSFER+CASH_OUT, 2.77M행). 잔액 모순(`errorBalanceOrig/Dest`)·금액 비율·타입 one-hot 12+1 피처. 홀드아웃 554K에서 ROC-AUC 0.9991 / PR-AUC 0.9981 / 큐 리콜 99.7% / 큐 FPR 0.0%. fraud-service 정합화는 W5.5-#4)
- (✅ ROADMAP W5.5-#4 — fraud-service 입력 스키마 PaySim 정합화. `app/scoring/features.py:build_paysim_row` 가 학습기와 동일한 파생 규칙으로 단건 변환, `ensemble.py:score_paysim_bundle` 이 IF→RF 합성 추론 단일 경로 제공, `routes_score.py` 가 `bundle.domain==paysim` 분기. `_normalize_anomaly` 는 도메인별 `ANOMALY_RANGES` dict 로 분리(open: -0.5~-0.05, paysim: -0.70~-0.35, 검증된 분포 기반))

#### Track 2. 사기 시나리오 시뮬레이터 + 검출률 측정
- **결손**: "어떤 사기 유형을 몇 % 잡는가" 에 대한 정량 답변 부재. 룰 엔진 10개가 어떤 시나리오를 커버하는지 측정 체계 없음
- **추가**: `fraud-service/app/services/scenario_generator.py` — **보이스피싱·머니뮬·계정탈취·카드 테스팅** 4개 시나리오 트랜잭션 합성기 (각 100건). 기존 [`routes_simulate.py`](fraud-service/app/api/routes_simulate.py) 의 `/v1/simulate/batch` 를 그대로 재사용해 신규 평가 로직 없음. 새 라우터 `routes_scenario.py` 가 검출률 집계만 담당
- **산출물**: 시나리오별 `BLOCK + REVIEW` 비율 = 검출률 표. 발표 슬라이드의 "사기 유형별 검출률" 근거 자료
- **코드 변경 위치**: 신규 파일 2개 (`scenario_generator.py`, `routes_scenario.py`) + [`main.py`](fraud-service/app/main.py) 라우터 1줄 등록
- **작업량**: 4~5시간 (반나절). 발표 직전 투입 가능한 유일한 트랙
- (✅ ROADMAP W5.5-#1 — `scenario_generator.py` 4종 합성기 + `POST /v1/scenario/run` 검출률 집계 라우터 + 결정적 시드. 100건/시나리오 스모크에서 4종 모두 BLOCK/REVIEW=100%, ≥80% 강건 회귀는 W5.5-#7)
- (✅ ROADMAP W5.5-#7 — `tests/test_scenario_regression.py` 시나리오별 ≥80% 검출률 + dominant fraud_type ≥50% 강건 회귀 테스트 9개. velocity 의존 룰 발동을 위해 `profile_store` 시드(머니뮬·카드테스팅 user_id 6~8건). 결과: 4종 모두 100% 검출, fraud_type 적중률 VOICE_PHISHING 75%·MONEY_MULE/ACCOUNT_TAKEOVER/CARD_TESTING 100%)
- (✅ ROADMAP W5.5-#8 — 운영 모델 PaySim 전환. `train_paysim.py --split-by-step` 시간순 split + `--no-leakage` ablation 옵션. 풀 데이터(2.77M행, 시간 step<354=학습/≥354=검증) 시간순 split AUC 0.99999~1.0 — 누수 피처(errorBalance*) 제거 후에도 동등 성능, 즉 PaySim 신호가 raw balance 기반으로 정직하게 분리됨을 입증. `routes_fraud._evaluate_one` 와 Kafka `_process_message` 모두 평가 직후 `profile_store.ingest` 자동 호출 — VelocityRule 등 profile-의존 룰이 운영에서 자연스레 발동. `MODEL_PATH` 기본값 `model_bundle_paysim_time_clean.joblib` 로 .env / docker-compose 전환)

#### Track 3. 사기 유형 다중분류 (binary → multiclass)
- **결손**: 현재 `final_action ∈ {PASS, SOFT_REVIEW, REVIEW, BLOCK}` 4단계만 있고 사기 *유형* 라벨이 없음. 사용자에게 "왜 차단되었는가"를 사기 유형으로 설명할 수 없음
- **추가**: `fraud_type ∈ {VOICE_PHISHING, MONEY_MULE, ACCOUNT_TAKEOVER, CARD_TESTING, AMOUNT_ANOMALY, BLACKLIST, NORMAL}` 필드를 룰별 매핑으로 도입. (BLACKLIST 는 W5.5-#5 구현 시 운영 라벨로 추가됨) 예: `VelocityRule + SplitTransactionRule → CARD_TESTING`, `ForeignIpRule + AmountReviewRule → ACCOUNT_TAKEOVER`. XAI Reason Code(#7)와 결합해 한국어 라벨로 설명 출력
- **코드 변경 위치**: [`policy_merge.py`](fraud-service/app/services/policy_merge.py) 에 룰→유형 매핑 테이블, [`routes_fraud.py`](fraud-service/app/api/routes_fraud.py) 응답 스키마에 `fraud_type` 필드 추가
- **의존성**: Track 1 또는 Track 2 선행 권장 (시나리오 라벨이 있어야 매핑 검증 가능)
- **작업량**: 3일
- (✅ ROADMAP W5.5-#5 — `policy_merge.classify_fraud_type(rule_ids)` 매핑 함수 + `FRAUD_TYPES`/`FRAUD_TYPE_LABELS_KO` 7종 라벨. 우선순위: BLACKLIST > CARD_TESTING(SPLIT_TXN/velocity-only) > ACCOUNT_TAKEOVER(FOREIGN_IP/DEVICE) > MONEY_MULE(velocity+amount) > VOICE_PHISHING(TIME_RISK+amount) > AMOUNT_ANOMALY > NORMAL. `routes_fraud.py /v1/fraud/evaluate` 응답에 `fraud_type` + `fraud_type_label` 필드 노출)
- (✅ ROADMAP W5.5-#6 — `train_paysim.py` 에 `--smote` / `--smote-k-neighbors` 옵션 추가. SMOTE 활성 시 train fold 사기를 정상과 1:1 로 오버샘플 후 RF 학습(class_weight 자동 비활성). 300K 샘플 비교: PR-AUC 0.99586(class_weight=balanced) vs 0.99632(SMOTE) — PaySim 신호가 강해 실효 차이 작지만 SMOTE FPR 약간 증가(1→10). 메트릭 JSON 두 모드 모두 트래킹)

#### Track 4. 송금 그래프 피처
- **결손**: 단일 거래 단위 평가만 있고 거래 *네트워크* 단위 평가 없음. 머니뮬 hub-and-spoke 패턴, 신규 수취인 비율, 1차 이웃 사기율 같은 그래프 시그널 부재
- **추가**: `fraud-service/app/services/graph_features.py` 신설. 인메모리 dict 기반 (NetworkX 도입은 옵션). [`behavioral_signals.py`](fraud-service/app/services/behavioral_signals.py) 와 같은 layer-1 위치에서 `_evaluate_one` 파이프라인에 합류. 추출 피처 예: `dest_first_seen_within_hours`, `dest_inbound_velocity`, `is_dest_high_risk_cluster`
- **의존성**: Track 1 (PaySim 도입) **필수** — Kaggle creditcard.csv에는 송금자/수취자 컬럼 자체가 없어 그래프 구성 불가
- **작업량**: 1~2주
- (✅ ROADMAP W6.5-#1 — `app/services/graph_store.py` 송금 그래프 store 구현. Redis sorted set 양방향 인덱스(`graph:inbound:{receiver}`, `graph:outbound:{sender}`) + 윈도우 TTL + in-memory deque 폴백 (device_store 패턴). `evaluate` flow 와 Kafka consumer 양쪽에서 평가 직후 자동 적재. `FraudEvaluateRequest` 에 `receiver_id` / `nameDest` 필드 추가. `inbound/outbound/fan_in_count/inbound_amount/first_seen_ts` API. W6.5-#2 graph_features 가 즉시 활용 가능)
- (✅ ROADMAP W6.5-#2 — `app/services/graph_features.py` 그래프 피처 추출기. 6종 피처 — `dest_first_seen_within_24h`, `dest_inbound_velocity_1h`, `fan_in_count`, `pass_through_ratio`, `inbound_amount`, `sender_outbound_amount`. `_evaluate_one` 가 store 적재 *전* 시점에서 호출 → 과거 윈도우 컨텍스트 보장. tx_data 와 응답 양쪽에 `graph_features` 노출 — W6.5-#3 MoneyMuleRule, W6.5-#4 LayeringRule 의 입력)
- (✅ ROADMAP W6.5-#5 — `FraudServiceManager.get_model_action` 에 비용 가중 결합. expected_loss = score × amount → COST_BLOCK_KRW(기본 3M)/COST_REVIEW_KRW(기본 500k) 임계값 적용 후 score-band action 과 `merge_actions` 로 더 강한 쪽 채택. evaluate 응답에 `expected_loss` 필드 노출. 1만원 거래의 0.99 score 와 1억원의 0.5 score 를 차별 처리)
- (✅ ROADMAP W6.5-#6 — `policy_merge.FRAUD_TYPE_BLOCK_THRESHOLDS` 딕셔너리 + `apply_fraud_type_threshold` 헬퍼. 룰 시그널 강한 유형(MONEY_MULE 0.5, CARD_TESTING 0.7, VOICE_PHISHING 0.6, ATO 0.65) 은 낮은 score 에서도 BLOCK 으로 승격, 보수적 유형(AMOUNT_ANOMALY 0.85)은 그대로. NORMAL=1.01 로 절대 미적용. routes_fraud._evaluate_one 에서 fraud_type 식별 직후 final_action 에 적용)

#### 우선순위 및 일정
| 시점 | 트랙 | 비고 |
|---|---|---|
| 중간 발표 직전 | Track 2 | 검출률 표를 발표 슬라이드 6 근거로 활용 |
| 5월 | Track 1 → Track 3 | 데이터셋 교체 후 다중분류 |
| 6월 | Track 4 | PaySim 송금 그래프 피처 |

#### Q&A 답변 매핑
| 예상 질문 | 답변 트랙 | 한 줄 답변 |
|---|---|---|
| "이게 진짜 사기 탐지가 맞나요?" | Track 1 | 현재는 카드결제 이상 스크리닝, 5월 PaySim 송금 데이터셋 교체로 송금 사기 도메인 확장 |
| "어떤 사기 유형을 잡나요?" | Track 2 | 보이스피싱·머니뮬·계정탈취·카드 테스팅 4개 시나리오 검출률 측정 체계를 구축, 평균 X% 검출 |
| "그냥 이상치 탐지 아닌가요?" | Track 3 | 사기 유형별 다중분류 라벨(`fraud_type`) 도입으로 유형 식별까지 확장 예정 |
| "관계·네트워크 분석은 없나요?" | Track 4 | PaySim 도입 후 송금 그래프 피처(수취인 신규성·hub-spoke 패턴)를 layer-1에 추가 예정 |

---

### 예상 질문 & 답변 (발표 Q&A 대비)

> 도메인 확장 관련 질문은 위 [도메인 확장 로드맵](#도메인-확장-로드맵-이상-거래-스크리닝에서-fds로) 절의 Q&A 매핑 표 참고.

**Q1. 왜 IF + XGBoost 가중평균인가요? 단일 모델로는 안 되나요?**
> XGBoost는 학습된 사기 패턴에 강하지만 학습 데이터에 없는 신종 패턴에 취약하고, IF는 그 반대입니다. 두 모델을 0.7/0.3 가중 평균하면 **"본 적 있는 패턴 + 본 적 없는 이상치"** 양쪽을 커버. IF 실패 시 XGB 단독 점수로 자동 폴백되어 가용성도 확보.

**Q2. ALPHA=0.7, BETA=0.3 가중치는 어떻게 결정했나요?**
> 현재는 도메인 휴리스틱(부스팅 모델 신뢰도가 높다는 가정)으로 하드코딩. ⑤절에서 지적한 대로 데이터 분포 변화 시 재조정이 어려운 약점이 있어, `.env`/`SYSTEM_CONFIG`로 빼고 A/B 테스트(#18)로 자동 튜닝하는 후속 작업이 정리돼 있습니다.

**Q3. 4단계 임계값(0.95/0.35/0.005)은 어떻게 정했나요?**
> Kaggle creditcard.csv와 IEEE-CIS 데이터셋의 holdout 셋에서 **PR-AUC를 최대화하는 지점**으로 튜닝. 0.005는 P99(상위 1% 잠재 위험군) 기준이라 SOFT_REVIEW로 떨어뜨려 모니터링 큐에만 올림.

**Q4. 왜 PR-AUC인가요? ROC-AUC가 더 일반적이지 않나요?**
> 사기 거래는 전체의 0.17% 수준 극단적 불균형이라 ROC-AUC는 false positive를 과소평가합니다. PR-AUC는 양성 클래스에 더 민감해서 **불균형 분류에서 모델 선택 기준으로 더 적합**.

**Q5. 모델과 룰이 충돌하면 어느 쪽이 우선?**
> `policy_merge.py`의 max-rank 정책 — 둘 중 더 강한 action을 따름(BLOCK > REVIEW > SOFT_REVIEW > PASS). 즉 모델이 PASS여도 룰이 BLOCK이면 BLOCK. 단점은 룰 false positive가 많을 때 사용자 경험 손상이라 향후 룰별 정확도 가중 정책으로 진화 여지 있음.

---

## ⑥ 한 줄 정리

부스팅 트리(학습된 사기 패턴)와 Isolation Forest(본 적 없는 이상치)를 0.7/0.3 가중 평균으로 결합한 뒤, 모델/규칙 중 강한 쪽을 따르는 max-rank 정책으로 PASS/SOFT_REVIEW/REVIEW/BLOCK 4단계를 결정하는 — 단순하지만 다층적인 실시간 사기 점수 시스템.
