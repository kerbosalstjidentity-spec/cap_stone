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

### 4.3 출력 해석

- **ROC-AUC**, **PR-AUC**: 순위·불균형 분류에서 흔히 쓰는 지표.
- **classification_report**: 확률을 **0.5로 잘랐을 때**의 정밀도·재현율. 검증 구간 사기 건수가 매우 적으면 지표가 **불안정**할 수 있다.

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

### 8.5 한계·향후 (실서비스와의 거리)

- 본 프로젝트는 **공개 벤치마크·오픈 CSV** 범위이며, **시간 순 검증**, 라벨 지연·정책 변경, 실시간 지연·비용 구조, 모니터링 등은 다루지 않았다.
- 따라서 여기서의 “권장 모델”은 **오프라인 비교 규칙 + 재현 가능한 수치**에 해당하며, **실서비스 도입 = 자동 차단**으로 바꿔 말할 수는 없다. 운영 환경에서는 규칙·점수·인적 검토·임계값·비용을 함께 설계하는 것이 일반적이다.
- **보완(후속)**: `scripts/fds/` 및 `docs/FDS_*.md`에 **배치 스코어링·규칙·임계값·모니터·드리프트·홀드아웃 지표**를 프로토타입 수준으로 정리했다. 보고서용 문단 템플릿은 `docs/FDS_THESIS_SNIPPETS.md`, IEEE-CIS 실험과의 역할 구분은 `docs/FDS_IEEE_CIS_CROSSWALK.md`를 참고한다.
