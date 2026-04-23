# FDS 1차 범위·성공 기준 (고정안 v1)

**문서 목적**: 초기 실험(모델 가능성·블렌딩 결론) 이후, **무엇을 맞추면 성공인지**와 **모의 데이터 방향**을 한 곳에 고정한다.  
**상태**: v1 — §2.4에 **표준 파이프라인**으로 채운 측정 스냅샷이 있음(재실행 시 변동 가능). 팀·지도와의 최종 목표 숫자는 여전히 합의 대상.

---

## 1. 막을 이벤트 (범위)

| 항목 | 1차(v1) 고정안 | 비고 |
|------|----------------|------|
| **이벤트** | **카드 결제(승인 요청) 시점** 한 건을 단위로 탐지 | 로그인·계정 탈취 등은 v1 범위 밖 |
| **채널** | **미구분(전 채널 동일 정책 가정)** | 실제 서비스에서는 `channel` 분리 가능; 모의 스키마에는 컬럼만 예약 |
| **라벨 정의** | `is_fraud = 1` = **사기로 확정된 거래**(규칙·분쟁·수동 확인 등 출처는 `label_source`로 구분) | 지연 라벨은 별도 문서에서 `label_ts` 기준 정의 |

**v1에서 하지 않는 것 (명시적 제외)**  
- 로그인·OTP·비밀번호 재설정 등 **비결제 이벤트**  
- **실시간 API 연동** (다음 단계: 배치·준실시간 프로토타입에서 다룸)

---

## 2. 성공 기준 (비즈니스 문장 → 측정)

아래는 **운영 가정을 숫자로 번역한 예시**이다. 괄호 안은 채울 값.

### 2.1 검토 큐 상한 + 재현

- **문장**: “**일 검토 큐 ( )건 이하**를 넘기지 않으면서, **실제 사기의 ( )% 이상**을 검토 큐(또는 차단+검토 합산)에 포함한다.”
- **측정 단위**: 일 단위로 집계하거나, 캡스톤에서는 **홀드아웃/시간 분할 테스트 구간**에서 동일 논리로 근사한다.
- **프로젝트 데이터에 대한 해석**: 공개 데이터에는 “검토 인력”이 없으므로, 보고서·실험에서는 **“상위 의심 K건”** 또는 **점수 임계값**으로 위 문장을 **오프라인으로 재현**한다 (`outputs/creditcard/if_eval_summary.csv` 등의 K·k% 설정과 연결).

### 2.2 정상 오탐 상한 (선택이지만 권장)

- **문장**: “정상 거래 중 **의심 처리 비율(FPR)** 을 ( )% 이하로 유지한다.”
- **용도**: 재현율만 올리면 큐가 터지므로, **정책 밴드**를 잡을 때 균형 축으로 쓴다.

### 2.3 v1에서 고정할 숫자 (초안 목표 — 팀 확인·수정)

아래는 **§2.4 실측**을 참고해 둔 **작업 초안**이다. 지도·팀 합의 후 숫자를 바꾼다.

| 지표 | 초안 목표 | 근거·비고 |
|------|-----------|-----------|
| 검토 큐 상한(프록시) | **≤ 300건/배치** (또는 test 구간 **≤ 284건** REVIEW+BLOCK) | §2.4: REVIEW 273 + BLOCK 11. 일자 컬럼 없어 “일 단위”는 배치 단위로 근사. |
| 사기 재현율(Recall) 하한 | **합의 후 기입** (참고: 홀드아웃 큐 내 **~67%**, 사기 **6건** 소표본) | `metrics_open_val_holdout.json` — 보고서에 소표본 한계 명시 |
| 정상→큐 FPR 상한 | **≤ 0.05%** (초안) | §2.4 홀드아웃에서는 0%; 운영에서는 여유 상한을 두고 튜닝 |

### 2.4 측정 스냅샷 (자동 파이프라인 기준)

다음은 `py -3 scripts/fds/pipeline_open_standard.py` 로 생성한 **open 데이터** 기준이다.  
상세 JSON: `outputs/fds/metrics_open_val_holdout.json`, `outputs/fds/monitor_open_test_full.json`.

| 구분 | 측정값 | 비고 |
|------|--------|------|
| **모델 검증** | 홀드아웃 ROC-AUC ≈ **1.000**, PR-AUC ≈ **0.976** | `val`의 **20% stratified 홀드아웃**, 학습은 나머지 80%만 사용 (`metrics_open_val_holdout.json`). |
| **정책 임계값** | `review_min=0.35`, `block_min=0.95` | `policies/fds/thresholds_v1.yaml` |
| **홀드아웃에서 검토+차단 큐** | 큐에 들어간 건수 **4** / 홀드아웃 **5,693**건 | 사기 라벨 **6건**뿐이라 Recall·FPR은 **참고용 소표본** |
| **홀드아웃 큐 내 Recall** | 약 **66.7%** (4/6) | 큐에 안 잡힌 사기 2건 |
| **홀드아웃 정상→큐 FPR** | **0%** (해당 실행 기준) | FP 0 |
| **test 전체 배치** | 행 **142,503** — PASS **142,219**, REVIEW **273**, BLOCK **11** | 번들은 **val 전체** 학습 (`model_bundle_open_full.joblib`) |
| **검토 큐 파일 행 수** | **273** | `export_review_queue`는 기본 REVIEW만 (`review_queue_open_test_full.csv`) |
| **승인 프록시(PASS 비율)** | 약 **99.80%** | `monitor_open_test_full.json` |

**해석 주의**: test에는 라벨이 없어 “사기 재현율”을 test에서 직접 쓰지 않는다. 보고서에는 **홀드아웃 지표**와 **큐·승인율(무 라벨)** 을 역할별로 구분해 서술한다.

### 2.5 드리프트 알람 해석 (A4 — 보고서용 한 줄)

`ops_drift.py` 결과 **V30**에서 PSI가 임계를 넘은 경우(예: train 대비 test 샘플): “**V30 분포가 학습 대비 현저히 달라졌을 가능성** — 재학습·특성 안정성·데이터 파이프라인 점검 대상” 정도로 서술한다. 단일 컬럼 알람이므로 **원인 단정은 하지 않고** 후속 분석 항목으로 남긴다.

---

## 3. 데이터 자세 (연구 vs 모의 운영)

| 구분 | 역할 | 이 레포에서의 위치 |
|------|------|-------------------|
| **공개 데이터** | 모델·임계값 스윕·블렌딩 등 **연구·재현** | `data/creditcard.csv`, `data/open/`, (선택) `data/ieee-cis/` |
| **모의 사내 스키마** | FDS 프로토타입 입력·출력을 **버전 관리**하기 위한 표준 | 본 문서 §4 + `docs/fraud_dataset_schema_reference.md` |

**원칙**: 공개 CSV 컬럼명을 그대로 운영에 가정하지 않고, **논리 스키마(v0)** 로 매핑한다.

---

## 4. 모의 스키마 v0 (프로토타입 입력)

`docs/fraud_dataset_schema_reference.md`의 **핵심 부분집합**을 v0로 둔다.

### 4.1 필수 (스코어링 잡이 반드시 읽는 컬럼)

| 논리 컬럼 | 타입 (예) | 설명 |
|-----------|-----------|------|
| `transaction_id` | string | 거래 고유 ID |
| `event_ts` | datetime (UTC) | 거래 시각 (없으면 연구용으로 상대 `Time` 초 단위 허용) |
| `amount` | number | 거래 금액 |

### 4.2 모델 특성 (v0)

- **풍부 도메인이 없을 때**: `V1`–`V28` 등 **익명 수치 특성**을 그대로 특성으로 둔다 (현재 Kaggle 카드 데이터와 동형).
- **결측 규칙**: 스키마 버전별로 “허용 결측 컬럼·대체값”을 **한 테이블**로 관리한다 (다음 단계: `schema v1` 문서 또는 YAML).

### 4.3 라벨 (학습·평가용, 스코어링 입력에서는 생략 가능)

| 컬럼 | 설명 |
|------|------|
| `is_fraud` | 0/1 |
| `label_ts`, `label_source` | 있으면 지연·편향 서술에 유리 |

### 4.4 스코어링 출력 (프로토타입 산출물)

배치 잡의 최소 출력:

| 컬럼 | 설명 |
|------|------|
| `transaction_id` | 입력과 동일 |
| `score` | 모델 점수 (0~1 또는 이상치 점수 — 버전 문서에 정의) |
| `reason_code` | 상위 기여 특성 구간·버킷 코드 (예: `HIGH_AMOUNT`, `V3_TOP_DECILE`) |

---

## 5. 버전·변경 이력

| 버전 | 날짜 | 요약 |
|------|------|------|
| v1 | 2026-03-22 | 1차 범위·모의 스키마·표준 파이프라인·§2.4 측정 스냅샷 |

---

## 6. 합의 체크리스트

- [ ] 이벤트 범위(카드 결제만 / 제외 범위)에 동의  
- [ ] 성공 기준 문장에 숫자(큐 상한·Recall·FPR) 기입  
- [ ] 공개 데이터는 연구용, 모의 스키마 v0를 프로토타입 기준으로 사용한다고 합의  
- [x] 배치 스코어링·스키마 v1·v2 모의·표준 파이프라인 (담당·일정은 팀 기록)

---

## 7. FDS 프로토타입 구현 위치 (2~4단계)

**상세 실행·SLO·드리프트 절차**: `docs/FDS_OPERATIONS_RUNBOOK_V1.md`

| 단계 | 구분 | 경로 |
|------|------|------|
| 2 | 스키마 YAML | `schema_v1_open.yaml`, `schema_v1_creditcard.yaml`, 모의 **`schema_v2_open_mock.yaml`** (`docs/FDS_V2_MOCK.md`) |
| 2 | 학습·번들 | `train_export_rf.py` → `model_bundle_open_eval.joblib`(홀드아웃), `model_bundle_open_full.joblib`(val 전체). 일괄: `pipeline_open_standard.py` |
| 2 | 배치 스코어 | `scripts/fds/batch_score.py`, 공용 `scoring.py` |
| 2 | 스키마·요약 특성 | `schema.py`, `reason_codes.py` |
| 3 | 규칙 선행 | `policies/fds/rules_v1.yaml`, `scripts/fds/rules_engine.py` |
| 3 | 임계값 밴드 | `policies/fds/thresholds_v1.yaml`, `batch_decide.py`, `policy_merge.py` |
| 3 | 규칙+모델 통합 | `scripts/fds/batch_run.py` → `final_action`, `audit_summary` |
| 3 | 검토 큐 추출 | `scripts/fds/export_review_queue.py` |
| 4 | 처리량 벤치 | `scripts/fds/ops_benchmark.py`, 목표 `policies/fds/ops_targets_v1.yaml` |
| 4 | 모니터링 요약 | `scripts/fds/ops_monitor.py` |
| 4 | 특성 드리프트 | `scripts/fds/ops_drift.py` (PSI·평균σ) |
| 4 | 성능 드리프트 | `scripts/fds/ops_labeled_metrics.py` (AUC·PR-AUC 스냅샷) |
| D | 준실시간 API | `scripts/fds/api_score_app.py`, `run_api.ps1` |
| D | SHAP 샘플 | `scripts/fds/ops_shap_sample.py` |

**예시 (프로젝트 루트):**

```text
py -3 scripts/fds/pipeline_open_standard.py
py -3 scripts/fds/train_export_rf.py --schema schemas/fds/schema_v1_open.yaml --train-csv data/open/val.csv --out outputs/fds/model_bundle_open_full.joblib
py -3 scripts/fds/batch_score.py --bundle outputs/fds/model_bundle_open_full.joblib --input data/open/test.csv --output outputs/fds/scores_open_test.csv
py -3 scripts/fds/batch_decide.py --scores outputs/fds/scores_open_test.csv --output outputs/fds/decisions_open_test.csv
py -3 scripts/fds/batch_run.py --schema schemas/fds/schema_v1_open.yaml --input data/open/test.csv --bundle outputs/fds/model_bundle_open_full.joblib --output outputs/fds/decisions_full_pipeline.csv
```

대용량 스모크: `train_export_rf.py --nrows N`, `batch_score.py` / `batch_run.py --nrows N`.

---

## 8. 관련 문서

- **이후 할 일(로드맵 체크리스트)**: `docs/FDS_NEXT_STEPS.md`  
- **v2 모의 스키마·CSV**: `docs/FDS_V2_MOCK.md`  
- **보고서 스니펫(A2·A3·A4)**: `docs/FDS_THESIS_SNIPPETS.md`  
- **IEEE-CIS 연계**: `docs/FDS_IEEE_CIS_CROSSWALK.md`  
- **산출물 보존 템플릿**: `docs/FDS_OUTPUT_RETENTION.md`  
- **선택 의존성(API·SHAP)**: `requirements-fds-optional.txt`  
- 운영 런북 (3~4단계 명령·SLO): `docs/FDS_OPERATIONS_RUNBOOK_V1.md`  
- 이상적 특성 체크리스트: `docs/fraud_dataset_schema_reference.md`  
- 기술·실험 요약: `docs/FRAUD_DETECTION_REPORT.md`  
- IEEE-CIS 파이프라인 예시: `scripts/ieee-cis/fds.py`  
- 스크립트 표: `scripts/README.md` (`fds/` 절)
