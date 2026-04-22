# 신용카드 거래 사기 탐지 — 기술·비즈니스 보고서

## 0. Executive summary

Kaggle 신용카드 사기 벤치마크 등 공개 데이터를 사용해, **라벨 없이 학습하는 비지도 이상 탐지(Isolation Forest)**와 **라벨을 사용하는 지도 학습(Random Forest·LightGBM, IF 점수 결합 포함)**을 실험했다. 별도 공개 과제는 `data/open/`에 대해 **지도 Random Forest**로 검증·제출 파일을 만든다.

- **비지도**는 “평소와 다른 패턴”을 의심 거래로 두는 **1차 스크리닝**에 적합하며, 재현율·정밀도·정상 오탐(FPR) 사이 **트레이드오프**가 분명하다.
- **지도**는 “과거에 사기로 확정된 사례와 비슷한가”를 학습하며, **ROC-AUC·PR-AUC** 등으로 비교하기 쉽다. 다만 **라벨 품질·양**이 성능을 좌우한다.
- **Kaggle 리더보드(지도·앙상블)**와 숫자만 직접 비교하는 것은 부적절하다. 비지도는 **문제 정의(학습에 라벨 미사용)**가 다르기 때문이다.

---

## 1. 프로젝트 구조 (파일 정리)

| 구분 | 경로 |
|------|------|
| 비지도 실험 (전체) | `scripts/creditcard/if_unsupervised.py` → 요약 `outputs/creditcard/if_eval_summary.csv` |
| 비지도 실험 (경량) | `scripts/creditcard/if_holdout.py` |
| 비지도 데모 (한 번 fit) | `scripts/creditcard/if_demo.py` |
| 비지도+지도 결합 (홀드아웃) | `scripts/creditcard/hybrid_if_rf.py` → `outputs/creditcard/hybrid_if_rf_compare.csv` |
| 비지도+지도 결합 (**CV 권장**) | `scripts/creditcard/hybrid_if_rf_cv.py` → `outputs/creditcard/hybrid_if_rf_cv_compare.csv`, `outputs/creditcard/hybrid_if_recommendation.txt` |
| 지도 학습 (open 데이터) | `scripts/open/supervised_rf.py` → `data/open/submission_supervised*.csv` |
| 원본 데이터 | `data/creditcard.csv`, `data/open/*.csv` |

---

## 2. 데이터

### 2.1 `data/creditcard.csv`

- Kaggle 신용카드 사기 데이터.
- `Class`: 0 정상, 1 사기. **비지도 학습의 `fit`에는 사용하지 않고**, 홀드아웃 평가·지표 계산에만 사용한다.

### 2.2 `data/open/`

- `train.csv`: 특성만 있고 **Class 없음** (지도 학습의 정답으로 쓰지 않음).
- `val.csv`: **Class** 포함 → 지도 학습·검증에 사용.
- `test.csv`: 제출용 ID + 특성.

---

## 3. 비지도 학습 (Isolation Forest)

### 3.1 목적

라벨을 **학습에 넣지 않고** 의심 거래를 식별하고, 홀드아웃에서만 사기 라벨과 비교해 **재현율·정밀도·FPR** 균형을 본다.

### 3.2 전처리 및 누수 방지

- `Amount`, `Time`은 **학습(train) 구간에만** `RobustScaler`로 적합하고, 검증(test)은 변환만 수행한다.
- `Time`, `Amount`, `Class`를 제외한 특성으로 `X`를 구성한다 (`scaled_amount`, `scaled_time` 및 V1–V28).

### 3.3 방법

- `sklearn.ensemble.IsolationForest`
- 학습: `X_train`만 (`Class` 미사용)
- 평가: `X_test` 예측과 `y_test` 비교

### 3.4 실험 구성 (요약)

| 구분 | 내용 |
|------|------|
| Part A | `contamination` 스윕 |
| Part B | `score_samples`로 하위 k%를 의심 |
| Part C | 가장 이상한 순으로 **K건**만 의심 (검토 인력 상한 가정) |

### 3.5 지표 정의

- **Positive**: 모델이 **의심(이상)**으로 본 경우.
- **Precision**: 의심 중 실제 사기 비율.
- **Recall**: 실제 사기 중 의심에 포함된 비율.
- **FPR(정상 중 오탐)**: 정상 거래 중 의심으로 잘못 분류된 비율.

`contamination`·k·K를 키우면 보통 Recall은 오르고 Precision은 내려가며 FPR은 오르는 경향이 있다.

### 3.6 결과 표

스크립트 실행 후 `outputs/creditcard/if_eval_summary.csv` 및 콘솔 출력을 보고서에 붙인다.

| experiment | setting | TP | FP | Precision | Recall | FPR_normal |
|------------|---------|----|----|-----------|--------|------------|
| *(실행 후 채움)* | | | | | | |

### 3.7 비기술 이해관계자용 숫자 해석 (요약)

테스트 구간에 사기가 극소수(예: 0.17% 전후)이면, 모델의 역할은 **“의심 목록을 줄여 사람이 볼 건수를 정하는 것”**에 가깝다. 의심 비율을 낮추면 정밀도는 올라가도 재현율은 떨어지고, 의심을 넓히면 재현율은 오르지만 정상 오탐이 늘어 검토 부담이 커진다.

### 3.8 한계

- 비지도는 **사기 정의를 직접 학습하지 않는다**. 지표는 튜닝·비교 참고용이다.
- Stratify 분할은 비율 유지용이며, 운영에서는 **시간 순 검증** 등이 필요할 수 있다.
- 데이터는 공개 벤치마크이며 실제 채널·라벨 지연은 반영하지 않았다.

### 3.9 Hybrid IF + RF/LGBM (`creditcard`) — 평가 기준 (프로젝트 기본안)

극단적 불균형에서는 **ROC-AUC만**으로 고르기보다 **PR-AUC**를 우선 보는 편이 보고서·실무 설명에 맞다. 다만 **한 번 나눈 홀드아웃** 숫자는 우연에 흔들릴 수 있으므로, 동일 파이프라인을 **Stratified 5-fold CV**로 돌린 뒤 **평균 PR-AUC 최대** 모델을 “권장”으로 둔다. (동률이면 평균 ROC-AUC가 큰 쪽.)

- 빠른 확인: `hybrid_if_rf.py` + `outputs/creditcard/hybrid_if_rf_compare.csv`
- 최종 비교 권장: `hybrid_if_rf_cv.py` + `outputs/creditcard/hybrid_if_rf_cv_compare.csv` 및 `outputs/creditcard/hybrid_if_recommendation.txt`

임계값 0.5 고정 리포트는 참고용이며, 운영 목표가 있으면 PR 곡선·비용에 맞춰 임계값을 따로 고르는 편이 낫다.

---

## 4. 지도 학습 (Random Forest, `data/open/`)

### 4.1 목적

`val.csv`에 **Class**가 있으므로, `V1`–`V30`만으로 사기 확률을 학습·검증하고, `test.csv`에 대한 제출 파일을 만든다.

### 4.2 데이터 제약

- `train.csv`에는 Class가 없어 **지도 학습의 정답으로 사용하지 않았다**.
- 학습·검증은 **라벨이 있는 `val.csv`만** 사용했다 (필요 시 train+val 병합 등은 과제 규칙에 따름).
- `val.csv`의 **사기 건수는 30건** (28,462행 중 0.105%)으로 극소수다. 이 때문에 단순 홀드아웃(80/20)은 테스트 세트에 사기 ≈ 6건만 남아 ROC-AUC·PR-AUC의 **통계적 신뢰도가 매우 낮다**.
- **대안**: `scripts/fds/train_export_rf.py --cv-folds 5`로 Stratified 5-fold CV를 사용하면 30건을 모두 평가에 활용하고 fold 간 분산도 확인할 수 있다.

### 4.3 출력 해석

- **ROC-AUC**, **PR-AUC**: 순위·불균형 분류에서 흔히 쓰는 지표.
- **classification_report**: 확률을 **0.5로 잘랐을 때**의 정밀도·재현율. 검증 구간 사기 건수가 매우 적으면 지표가 **불안정**할 수 있다.
- **단일 홀드아웃 결과 주의**: 사기 6건 홀드아웃에서 ROC-AUC ≈ 0.999가 나오더라도, 이는 샘플 수 부족으로 인한 **우연일 가능성이 높다**. 신뢰 가능한 지표는 CV 결과를 참고하라.

### 4.4 산출물

- `data/open/submission_supervised_proba.csv`: Class = 사기 **확률** (AUC 제출에 흔함).
- `data/open/submission_supervised.csv`: Class = **0 또는 1** (임계값 0.5).

---

## 5. 비지도 vs 지도 — 무엇이 다른가

| | 비지도 (IF) | 지도 (RF) |
|---|-------------|-----------|
| 학습 시 라벨 | 사용 안 함 | 사용 |
| 결과 | 이상 점수·의심 여부 | 사기 확률·0/1 |
| 질문 | “평소와 다른가?” | “확정 사기와 비슷한가?” |
| 보고서 지표 | Precision, Recall, FPR | ROC-AUC, PR-AUC |

---

## 6. 비즈니스·이해관계자용 한 단락

본 프로젝트는 학습 단계에서 사기 라벨을 쓰지 않는 Isolation Forest 기반 **비지도 이상 탐지**와, 라벨이 있는 검증 데이터를 사용하는 **지도 분류**를 함께 다룬다. 비지도 결과는 **의심 순위를 매기는 1차 필터**로 해석하는 것이 타당하며, 최종 차단·자동 거절까지의 성능으로 단정하기보다 **라벨·규칙·인적 검토**와 결합하는 단계가 필요함을 시사한다. 지도 모델은 라벨이 신뢰할 만큼 쌓일수록 운영 목표(미탐 vs 오탐 비용)에 맞추기 쉽다.

---

## 7. 재현 방법

```text
py -3 scripts/creditcard/if_unsupervised.py
py -3 scripts/creditcard/if_holdout.py
py -3 scripts/creditcard/if_demo.py
py -3 scripts/creditcard/hybrid_if_rf.py
py -3 scripts/creditcard/hybrid_if_rf_cv.py
py -3 scripts/open/supervised_rf.py
```

---

## 8. 결론

### 8.1 데이터·실험 범위

- **Kaggle `creditcard.csv`**: 비지도(IF)·지도·하이브리드(IF 이상 점수 + RF/LGBM)를 **동일한 누수 방지 전처리** 가정 하에 비교했다.
- **`data/open/`**: 라벨이 있는 `val.csv`로 지도 RF를 학습·검증하고, `test.csv`에 대한 **제출용 확률·0/1 파일**을 생성한다.
- 두 데이터셋의 숫자는 **서로 직접 비교하지 않는다**(특성·분포·과제 정의가 다름).

### 8.2 Kaggle — 하이브리드 지도 모델 평가

- 극단적 불균형을 고려해 **평균 PR-AUC를 1순위**, 동률이면 **평균 ROC-AUC**로 모델을 고르는 **프로젝트 기본안**을 적용했다.
- **Stratified 5-fold CV**(`scripts/creditcard/hybrid_if_rf_cv.py`, `random_state=42`) 결과, 네 구성(RF·LGBM × baseline·hybrid)의 평균 PR-AUC는 서로 **매우 근접**했다.
- 동일 CV 기준 **권장 모델**은 `outputs/creditcard/hybrid_if_recommendation.txt`에 기록된 대로 **`rf_baseline`**이다 (평균 PR-AUC 약 **0.854**, 평균 ROC-AUC 약 **0.957**; 세부는 `outputs/creditcard/hybrid_if_rf_cv_compare.csv` 참고).
- **단일 홀드아웃** 결과(`outputs/creditcard/hybrid_if_rf_compare.csv`)는 빠른 참고용이며, **최종 비교는 CV 표**를 우선한다. IF 점수를 특성으로 넣은 hybrid가 항상 우위라고 단정할 수는 없고, 이번 설정에서는 baseline RF가 평균 PR 기준으로 앞선다.

### 8.3 Kaggle — 비지도(IF)

- `contamination`·하위 k%·상위 K건 등 설정에 따라 **Precision–Recall–FPR**이 바뀌는 **트레이드오프**를 확인할 수 있다. 구체적 숫자는 `outputs/creditcard/if_eval_summary.csv` 및 `if_unsupervised.py` 실행 로그로 정리한다.
- 비지도는 **1차 스크리닝·의심 순위** 용도로 해석하고, 지도·하이브리드와 **문제 정의가 다름**을 유의한다.

### 8.4 `data/open/` — 지도 학습·제출

- `val.csv`로 학습·검증한 Random Forest의 ROC-AUC·PR-AUC와 `data/open/submission_supervised*.csv`는 **해당 과제(제출 형식·채점)** 맥락에서 사용한다.
- **신뢰 가능한 지표 (5-fold CV, `outputs/fds/metrics_open_cv5.json`)**:
  - ROC-AUC: **0.9625 ± 0.044** (fold별: 0.908 ~ 0.9997)
  - PR-AUC: **0.7891 ± 0.049**
  - Out-of-fold Recall (큐 기준): **76.7%**, FPR: **0.018%**
- **단일 홀드아웃 결과** (`metrics_open_val_holdout.json`, `model_bundle_open_fixed.metrics.json`)의 ROC-AUC ≈ 0.9999는 홀드아웃 사기 6건이라는 극소 샘플로 인한 것으로, **신뢰할 수 없는 수치**다 (해당 파일 내 `warning` 필드 참고).
- `metrics_baseline.json`의 ROC-AUC = 1.0은 **훈련 데이터 오염(train-test contamination)**: 80% val.csv로 훈련한 모델을 val.csv 전체(훈련 데이터 포함)에 평가한 결과다.
- **IEEE-CIS walk-forward** (`outputs/ieee_cis/walk_forward/fold_metrics.csv`): fold 1→4로 학습 데이터가 누적될수록 ROC-AUC 0.856 → 0.914로 향상되는 **긍정적 학습 경향**이 확인된다.

### 8.5 한계·향후 (실서비스와의 거리)

- 본 프로젝트는 **공개 벤치마크·오픈 CSV** 범위이며, **시간 순 검증**, 라벨 지연·정책 변경, 실시간 지연·비용 구조, 모니터링 등은 다루지 않았다.
- 따라서 여기서의 “권장 모델”은 **오프라인 비교 규칙 + 재현 가능한 수치**에 해당하며, **실서비스 도입 = 자동 차단**으로 바꿔 말할 수는 없다. 운영 환경에서는 규칙·점수·인적 검토·임계값·비용을 함께 설계하는 것이 일반적이다.
- **보완(후속)**: `scripts/fds/` 및 `docs/FDS_*.md`에 **배치 스코어링·규칙·임계값·모니터·드리프트·홀드아웃 지표**를 프로토타입 수준으로 정리했다. 보고서용 문단 템플릿은 `docs/FDS_THESIS_SNIPPETS.md`, IEEE-CIS 실험과의 역할 구분은 `docs/FDS_IEEE_CIS_CROSSWALK.md`를 참고한다.

---

### 8.6 실제 FDS와의 구조적 갭 분석

실제 운영 FDS(예: Visa, Mastercard, 카카오페이)와 본 프로젝트의 파이프라인을 구조적으로 비교한다.

#### 현재 구현 vs 실제 FDS

| 항목 | 현재 프로젝트 | 실제 운영 FDS |
|------|-------------|--------------|
| **입력 피처** | V1-V30 (PCA 익명), amount | 사용자 30일 패턴, 기기 지문, 가맹점 사기율, GPS/IP |
| **모델** | RF 단일 또는 RF+LGBM 앙상블 | 수십 개 모델 앙상블 + 그래프 뉴럴넷 |
| **규칙** | YAML 기반 6-10개 규칙 | 수백~수천 개 규칙 (국가별, 채널별, 시간대별) |
| **Velocity 피처** | tx_count_1h, amount_sum_24h 등 8개 (`velocity_features.py`) | Feature Store에서 수백 개 실시간 집계 |
| **결정 지연** | 배치 (수 ms~수 초) | < 100ms (실시간 결제 승인 타임아웃 내) |
| **검토 큐** | REVIEW 액션 CSV 추출 (`export_review_queue.py`) | 심사원 실시간 워크플로우 시스템 |
| **결제 연동** | `/v1/authorize` API (APPROVED/PENDING/DECLINED) | 실제 결제망(VAN, PG) 직접 연결 |
| **재학습 트리거** | PSI 드리프트 감지 → subprocess (`retrain_trigger.py`) | 자동 MLOps 파이프라인 (Airflow, Kubeflow 등) |
| **라벨 피드백** | `ops_labeled_metrics.py` (사후 배치 계산) | 실시간 거부 확정 → 즉시 학습 데이터 반영 |

#### 코드로 시뮬레이션 가능했던 것 ✅

- **Velocity Feature Store 시뮬레이션**: `velocity_features.py`에서 user_id·event_ts·amount·country 기반 집계 8개 피처를 DataFrame 내에서 계산. 실제 Feature Store의 역할을 단일 파일에서 재현.
- **결제 승인 API**: `api_score_app.py /v1/authorize`로 단건 스코어링 + 정책 결정을 100ms 내에 처리.
- **앙상블 모델**: `train_export_ensemble.py`로 RF + LightGBM 동시 학습, 평균 확률로 최종 스코어 산출.
- **MLOps 재학습 트리거**: `retrain_trigger.py`로 PSI critical(>0.25) 또는 major(>0.10) 3개 이상 감지 시 자동 재학습 실행.
- **Velocity 규칙**: `rules_v2_velocity.yaml`로 1시간 내 8건 초과 → BLOCK, 국가 변경 → REVIEW 등 운영 규칙 구현.

#### 인프라 없이 구현 불가한 것 ❌

- **실시간 Feature Store**: 수백만 사용자 × 수십 피처를 < 5ms에 서빙하려면 Redis/Flink 등 스트리밍 인프라 필요.
- **그래프 피처**: “같은 기기로 접속한 다른 계좌” → 그래프 DB(Neo4j, TigerGraph) 없이는 계산 불가.
- **가맹점 사기율 실시간 업데이트**: 가맹점별 사기 발생 이력이 실시간으로 누적·갱신되어야 함.
- **결제망 직접 연동**: VAN/PG 시스템과의 실제 API 연결 없이는 실시간 차단 불가.

#### 합성 데이터 한계 명시

본 프로젝트는 실제 카드 데이터 부재로 합성 데이터(`data/fds/synthetic_train.csv`, 30,000행)를 생성해 사용했다. 합성 데이터의 특성:
- 사기 피처(V14, V12, V10 등)에 통계적 이동(shift)을 적용해 분류 난이도를 제어했다.
- 실제 데이터 대비 피처 분리도가 과도하게 높아 ROC-AUC ≈ 0.9999가 나온다. **이는 합성 데이터 특성이지 모델 과적합이 아니다.**
- 파이프라인 end-to-end 검증 목적으로만 사용해야 하며, 실제 성능 예측에 사용하면 안 된다.

---

## 9. 실제 FDS 아키텍처 시뮬레이션 (v2 확장)

### 9.1 실제 FDS와의 갭 분석

실제 운영 FDS는 단순 모델 스코어를 넘어 여러 계층의 컨텍스트를 결합한다.

| 계층 | 실제 FDS | 본 프로젝트 구현 | 비고 |
|------|----------|----------------|------|
| 입력 | 거래 1건 + 사용자 30일 패턴 + 기기 연결 + 가맹점 사기율 | velocity_features.py (인메모리 시뮬레이션) | Feature Store 대체 |
| 모델 | 앙상블 N개 (RF·LGBM·NN·규칙 기반) | RF + LGBM 앙상블 (train_export_ensemble.py) | 2-model avg |
| 규칙 | 수백 개 (velocity·geography·behavioral) | rules_v1(기본 3개) + rules_v2_velocity(6개) | 9개 규칙 |
| 결정 | 결제 승인/거부 API 연동 | /v1/authorize (APPROVED/PENDING/DECLINED) | FastAPI mock |
| 심사 | 심사원 웹 UI + 라벨 피드백 | export_review_queue.py + REVIEW 큐 | 큐만 추출 |
| MLOps | 드리프트 감지 → 자동 재학습 | retrain_trigger.py (PSI 임계값 기반) | subprocess 호출 |
| 피드백 | 심사 결과 → 재학습 데이터 | ops_labeled_metrics.py (사후 AUC 재계산) | 라벨 수집 후 |

### 9.2 Velocity 피처 엔진

`scripts/fds/velocity_features.py`는 Feature Store 없이 판다스 in-memory 집계로 실시간 집계 피처를 시뮬레이션한다.

| 피처 | 설명 | 실제 FDS 의미 |
|------|------|--------------|
| `tx_count_1h` | 직전 1시간 거래 건수 | 카드 복제 감지 핵심 지표 |
| `tx_count_24h` | 직전 24시간 거래 건수 | 일별 이상 패턴 |
| `amount_sum_24h` | 24시간 누적 금액 | 일일 한도 초과 감지 |
| `amount_sum_7d` | 7일 누적 금액 | 서서히 증가하는 패턴 |
| `unique_countries_7d` | 7일 거래 국가 수 | 지리적 불일치 |
| `country_change_flag` | 직전 거래 대비 국가 변경 | 국가 점프 이상 |
| `tx_velocity_ratio` | `tx_count_1h / (tx_count_24h + 1)` | 급격한 거래 급증 |

> **한계**: 실제 Feature Store(Redis, Feast 등)는 밀리초 단위 조회가 필요하나, 본 구현은 배치 집계로 동일 로직을 표현한다.

### 9.3 RF + LGBM 앙상블

`train_export_ensemble.py`는 동일한 CV 파이프라인에서 RF와 LGBM을 병렬 학습하고 확률을 평균한다.

- 각 fold에서 RF·LGBM 독립 학습 → 확률 `(p_rf + p_lgbm) / 2`
- 단일 모델 대비 분산 감소, 특히 사기 건수가 적은 데이터에서 안정적
- 번들 형식: `{“ensemble”: True, “models”: [...], “ensemble_method”: “avg”}` → scoring.py가 자동 처리

### 9.4 결제 승인/거부 API

`/v1/authorize` 엔드포인트는 단건 거래에 대해 스코어링과 정책 결정을 한 번에 수행한다.

```
POST /v1/authorize
→ decision: APPROVED (PASS) / PENDING (REVIEW) / DECLINED (BLOCK)
→ score, reason_codes, threshold_used 함께 반환
```

실제 카드사 API와의 차이: 인증·레이턴시 SLA·결제 원장 연동 없음. 결정 로직은 동일.

### 9.5 자동 재학습 트리거

`retrain_trigger.py`는 드리프트 리포트를 읽어 재학습 필요 여부를 판단한다.

| PSI 조건 | 의미 | 트리거 |
|---------|------|-------|
| critical 피처 ≥ 1개 (PSI > 0.25) | 분포 심각 이탈 | 즉시 재학습 |
| major 피처 ≥ 3개 (PSI > 0.1) | 다수 피처 변화 | 재학습 |

`--dry-run` 플래그로 실제 재학습 없이 트리거 조건만 점검할 수 있다.

---

## 9. FDS 운영 파이프라인 — 검증 결과 및 설계

### 9.1 파이프라인 개요

`scripts/fds/`는 오프라인 실험에서 **운영 수준 배치 파이프라인**으로 확장한 모듈이다. 학습→스코어링→정책 결정→모니터링→드리프트 감지가 각각 독립적인 스크립트로 분리돼 있으며, YAML 기반 임계값·규칙 파일로 정책 변경 없이 코드 수정 없이 조정 가능하다.

| 단계 | 스크립트 | 산출물 |
|------|----------|--------|
| 학습·번들 생성 | `train_export_rf.py` | `model_bundle_*.joblib`, `metrics_*_cv5.json` |
| 배치 스코어링 | `batch_run.py` | `scores_*.csv` |
| 정책 결정 | `batch_decide.py` | `decisions_*.csv` (block/review/pass) |
| 운영 모니터 | `ops_monitor.py` | `monitor_summary.json` |
| 드리프트 감지 | `ops_drift.py` | `drift_*.json` (PSI 5등급) |
| 검토 큐 추출 | `export_review_queue.py` | `review_queue.csv` |
| 사후 성능 평가 | `ops_labeled_metrics.py` | `labeled_metrics.json` |

### 9.2 모델 검증 결과 (5-fold Stratified CV)

모든 지표는 **SMOTE를 각 fold 훈련 분할에만 적용**하고, 평가는 원본 분포의 검증 분할에서 산출한다. 최종 모델은 전체 데이터를 재학습해 번들에 저장한다.

#### open 데이터셋 (`data/open/val.csv`)

- 규모: 28,462행, 사기 30건 (0.105%)
- 특성: V1–V30 (PCA 익명화)
- 임계값: block ≥ 0.5, review ≥ 0.35

| 지표 | 값 |
|------|-----|
| ROC-AUC (평균 ± 표준편차) | **0.963 ± 0.044** |
| PR-AUC (평균 ± 표준편차) | **0.789 ± 0.049** |
| Out-of-fold Recall (큐 기준) | **76.7%** (30건 중 23건 포착) |
| Out-of-fold FPR (큐 기준) | **0.018%** (정상 오탐 5건) |

> **단일 홀드아웃 주의**: `metrics_open_val_holdout.json`의 ROC-AUC ≈ 0.9999는 홀드아웃 사기 6건에 의한 우연치다. 해당 파일 내 `warning` 필드 및 `metrics_baseline.json`의 ROC-AUC = 1.0 (훈련 데이터 오염)을 참고하라. **신뢰 지표는 CV 결과를 사용한다.**

#### IEEE-CIS 데이터셋

- 규모: 100,000행 (샘플), 사기 2,561건 (2.56%)
- 특성: V1–V339, TransactionAmt 등
- walk-forward fold 1→4 기준 ROC-AUC 0.856 → 0.914 (학습량 증가에 따른 향상)

| 지표 | 값 |
|------|-----|
| ROC-AUC (평균 ± 표준편차) | **0.893 ± 0.004** |
| PR-AUC (평균 ± 표준편차) | **0.615 ± 0.010** |
| Out-of-fold Recall (큐 기준) | **52.3%** |
| Out-of-fold FPR (큐 기준) | **0.47%** |

> IEEE-CIS는 특성 수(340+)와 사기 패턴 다양성이 커 PR-AUC가 낮다. 임계값 조정이나 추가 피처 엔지니어링으로 개선 여지가 있다.

### 9.3 드리프트 감지 설계 (PSI 기반)

`ops_drift.py`는 Population Stability Index(PSI)를 피처별로 계산하고 5등급으로 분류한다.

| PSI 범위 | 등급 | 조치 |
|----------|------|------|
| < 0.10 | stable | 무시 |
| 0.10 – 0.20 | watch | 모니터링 |
| 0.20 – 0.25 | warning | 재학습 검토 |
| 0.25 – 0.50 | alert | 재학습 권장 |
| ≥ 0.50 | critical | 즉시 재학습 |

PSI 계산 시 랜덤 샘플링(최대 10만 행)을 적용해 대용량 데이터에서도 안정적으로 동작한다.

### 9.4 정책 구조 (YAML)

`policies/fds/thresholds_v1.yaml` 및 규칙 파일로 정책을 코드 변경 없이 조정한다. 입력은 `schemas/`의 JSON Schema로 검증하며, 스키마 오류 시 파이프라인이 조기 종료된다.

```
block_min: 0.5    # 사기 확률 ≥ 0.5 → 자동 차단
review_min: 0.35  # 사기 확률 ≥ 0.35 → 수동 검토 큐
```

### 9.5 테스트 커버리지

| 테스트 파일 | 커버 대상 |
|-------------|-----------|
| `tests/test_e2e_pipeline.py` | schema→scoring→rules→policy_merge E2E 22건 |
| `tests/test_psi_calculation.py` | PSI 수학적 속성 6건 |
| `tests/test_ops_labeled_metrics.py` | ops_labeled_metrics 8건 |
| `tests/test_policy_merge.py` | 정책 병합 로직 |
