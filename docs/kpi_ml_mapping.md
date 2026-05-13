# 비즈니스 KPI ↔ ML 지표 매핑 (W8-#7)

## Why

ML 팀 KPI(AUC, F1, precision)와 비즈니스 KPI(사기 손실액, 고객 이탈)가
서로 다른 단위로 측정되면 "AUC 올렸는데 손실 증가" 같은 모순이 silent
로 진행된다. 본 문서는 두 측을 명시적으로 매핑한다.

## 핵심 매핑 표

| 비즈니스 KPI | 정의 | 연결되는 ML 지표 | 모니터링 위치 |
|---|---|---|---|
| **사기 손실액 (월간)** | 미검출 + 환불 손실 합 | recall (W7-#9 variant 별) × 평균 거래액 | `/admin/api/ab-precision-recall` |
| **고객 마찰** | step-up / 차단 받은 정상 사용자 | FPR (false_positive_rate) | `/admin/api/stats` action_distribution |
| **CS 처리비** | FP 1건당 처리 평균비 | FP × cost_per_fp (W8-#6 fp_cost_analyzer) | `fp_cost_analyzer.expected_fp_count_per_day` |
| **모델 신뢰도** | 운영 분포 vs 학습 분포 차이 | KS statistic, score p99 drift | `/admin/api/drift`, `/admin/api/score-distribution` |
| **모델 응답성** | p99 latency | inference latency | `/admin/api/latency`, `/admin/api/slo` |
| **사기 유형 커버리지** | 시나리오별 검출률 | per-scenario detection_rate | `/admin/api/slo` per_scenario |

## 손실/비용 계산식

### 미검출 손실
```
expected_loss_per_day
  = daily_traffic × fraud_base_rate × (1 - recall) × avg_fraud_amount
```

W7.5 PaySim 통계 기준:
- fraud_base_rate ≈ 0.13% (PaySim TRANSFER+CASH_OUT)
- avg_fraud_amount ≈ 800,000 원 (PaySim 평균)

### FP 비용
```
expected_fp_cost_per_day
  = daily_traffic × FPR × cost_per_fp_krw
```

W8-#6 의 `expected_fp_count_per_day()` 결과와 동일.

### 종합 운영 비용 함수
```
total_cost = expected_loss + expected_fp_cost
           = N × fr × (1-r) × amt + N × fpr × c
           = N × [ fr × (1-r) × amt + fpr × c ]
```

이 함수를 임계값(BLOCK threshold) τ 의 함수로 표현하면 운영 최적 τ\* 산출.
- τ ↑ → recall ↓ (손실 ↑) + FPR ↓ (비용 ↓)
- τ ↓ → 반대

현재 PayWise 는 `COST_BLOCK_KRW` / `COST_REVIEW_KRW` (W6.5-#5) 를 통해
expected_loss = score × amount 가 임계 초과 시 BLOCK — 즉 동적 τ 가 이미
비용 가중 형태로 구현. 본 문서는 그 결정 근거를 ML 지표와 명시 매핑.

## 알람 규칙

| 알람 | 조건 | 동작 | 구현 |
|---|---|---|---|
| recall 급락 | 일별 recall < 0.6 (variant 평균) | Slack #fraud-ops | W7-#9 + W7-#4 alarm_manager 확장 |
| FPR 급증 | FPR > 5% (일별) | 룰 일시 disable | `recommend_disable` (W8-#6) |
| latency p99 > 200ms | 10분 윈도우 | auto rollback | `alarm_manager` (W7-#4) |
| drift KS > 0.3 | 어떤 피처라도 | 모델 롤백 | `alarm_manager` (W7-#4) |

## 변경 이력

- 2026-05-10 W8-#7 — 초안 작성
