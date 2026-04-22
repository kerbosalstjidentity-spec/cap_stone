# 신용카드 사기 탐지 (캡스톤)

비지도(Isolation Forest)·지도(Random Forest) 실험과 **FDS(Fraud Detection System) 운영 파이프라인**을 포함한 저장소입니다.

---

## 폴더 구조

| 경로 | 설명 |
|------|------|
| `scripts/creditcard/` | Kaggle `creditcard.csv` — 비지도·하이브리드 실험 |
| `scripts/open/` | `data/open/` — 지도 학습·제출 파일 생성 |
| `scripts/fds/` | **FDS 운영 파이프라인** (학습·스코어링·규칙·모니터·드리프트) |
| `data/creditcard.csv` | Kaggle 벤치마크 (Time, Amount, V1–V28, Class) |
| `data/open/` | 별도 과제용 CSV (`train`/`val`/`test`) |
| `data/ieee-cis/` | IEEE-CIS 사기 탐지 데이터 (배치용) |
| `outputs/fds/` | 모델 번들·메트릭 JSON·드리프트 리포트 |
| `outputs/ieee_cis/` | IEEE-CIS walk-forward 실험 결과 |
| `policies/fds/` | YAML 임계값·규칙 파일 (rules_v1: 기본, rules_v2_velocity: velocity 기반) |
| `schemas/` | 입력 스키마 정의 |
| `docs/` | 기술·비즈니스 보고서 |
| `tests/` | 단위·통합 테스트 |

---

## FDS 파이프라인 실행 순서

### 1단계: Velocity 피처 생성 (실시간 집계 시뮬레이션)

```bash
# mock 데이터 생성 (user_id, event_ts, merchant_id 포함)
python scripts/fds/build_mock_v2_dataset.py \
  --output data/fds/mock_transactions_v2.csv

# velocity 피처는 scoring 단계에서 자동 적용 (velocity_features.py)
# tx_count_1h, tx_count_24h, amount_sum_24h, country_change_flag 등
```

### 1.5단계: 합성 학습 데이터 생성 (실제 데이터 없을 때)

```bash
# 학습용 합성 데이터 30k행 (1.5% 사기, 현실적 패턴)
python scripts/fds/build_mock_v2_dataset.py \
  --out data/fds/synthetic_train.csv \
  --nrows 30000 --fraud-rate 0.015 --realistic

# 데모용 mock 데이터 5k행 (velocity 규칙 테스트용)
python scripts/fds/build_mock_v2_dataset.py \
  --out data/fds/mock_transactions_v2.csv \
  --nrows 5000 --fraud-rate 0.015 --realistic --seed 99
```

> **주의**: 합성 데이터는 실제 카드 거래 패턴을 완전히 반영하지 않습니다.
> 실제 데이터 대비 ROC-AUC가 과도하게 높게 나올 수 있습니다.

### 2단계: 모델 학습 및 번들 생성

```bash
# 앙상블 모델 (RF + LGBM, 5-fold CV) — 합성 데이터 사용
python scripts/fds/train_export_ensemble.py \
  --schema schemas/fds/schema_v1_open.yaml \
  --train-csv data/fds/synthetic_train.csv \
  --out outputs/fds/model_bundle_synthetic_ensemble.joblib \
  --cv-folds 5

# 단일 RF (실제 open 데이터 있을 때)
python scripts/fds/train_export_rf.py \
  --schema schemas/fds/schema_v1_open.yaml \
  --train-csv data/open/val.csv \
  --out outputs/fds/model_bundle_open_cv.joblib \
  --cv-folds 5

# IEEE-CIS 데이터셋 (실제 데이터 있을 때)
python scripts/fds/train_export_rf.py \
  --schema schemas/fds/schema_v1_ieee_cis.yaml \
  --train-csv data/ieee-cis/train_transaction.csv \
  --out outputs/fds/model_bundle_ieee_cis_cv.joblib \
  --cv-folds 5
```

### 3단계: 배치 스코어링 + 규칙 평가

```bash
# 통합 배치 (스코어 + 규칙 + 정책 결정 한 번에)
python scripts/fds/batch_run.py \
  --bundle outputs/fds/model_bundle_open_cv.joblib \
  --schema schemas/fds/schema_v1_open.yaml \
  --input data/open/test.csv \
  --rules policies/fds/rules_v1.yaml \
  --thresholds policies/fds/thresholds_v1.yaml \
  --output outputs/fds/decisions_open.csv

# velocity 규칙 적용 시 (mock 데이터 기준)
python scripts/fds/batch_run.py \
  --bundle outputs/fds/model_bundle_open_cv.joblib \
  --schema schemas/fds/schema_v2_open_mock.yaml \
  --input data/fds/mock_transactions_v2.csv \
  --rules policies/fds/rules_v2_velocity.yaml \
  --thresholds policies/fds/thresholds_v1.yaml \
  --output outputs/fds/decisions_mock.csv
```

### 4단계: 준실시간 API (단건 승인/거부)

```bash
# 환경변수로 번들 지정 후 서버 실행
set FDS_BUNDLE_PATH=outputs/fds/model_bundle_open_cv.joblib
uvicorn scripts.fds.api_score_app:app --host 127.0.0.1 --port 8765

# 단건 결제 승인 요청 (APPROVED / PENDING / DECLINED)
curl -X POST http://127.0.0.1:8765/v1/authorize \
  -H "Content-Type: application/json" \
  -d '{"V1": -1.36, "V2": -0.07, ..., "V30": 0.12, "amount": 149.62}'

# 응답 예시:
# {"transaction_id": "api_0", "decision": "APPROVED", "score": 0.03, ...}
```

### 5단계: 모니터링 및 드리프트 감지

```bash
# 운영 지표 모니터
python scripts/fds/ops_monitor.py \
  --scores outputs/fds/decisions_open.csv \
  --output outputs/fds/monitor_summary.json

# PSI 기반 피처 드리프트 감지
python scripts/fds/ops_drift.py \
  --reference data/open/val.csv \
  --current data/open/test.csv \
  --bundle outputs/fds/model_bundle_open_cv.joblib \
  --output outputs/fds/drift_train_vs_test.json
```

### 6단계: 자동 재학습 트리거 (MLOps)

```bash
# 드리프트 리포트 기반 재학습 필요 여부 확인
python scripts/fds/retrain_trigger.py \
  --drift-report outputs/fds/drift_train_vs_test.json \
  --schema schemas/fds/schema_v1_open.yaml \
  --train-csv data/open/val.csv \
  --bundle-out outputs/fds/model_bundle_open_cv.joblib \
  --cv-folds 5 \
  --dry-run   # 실제 재학습 없이 트리거 조건만 확인

# --dry-run 제거 시 PSI critical/major 조건 충족 시 자동 재학습 실행
```

### 7단계: 검토 큐 추출 및 사후 성능 평가

```bash
# 검토 큐 (REVIEW 액션 필터)
python scripts/fds/export_review_queue.py \
  --decisions outputs/fds/decisions_open.csv \
  --output outputs/fds/review_queue.csv

# 라벨 확보 후 성능 재계산
python scripts/fds/ops_labeled_metrics.py \
  --scores outputs/fds/decisions_open.csv \
  --labels <실제라벨.csv> \
  --output outputs/fds/labeled_metrics.json
```

---

## 주요 검증 메트릭 (5-fold CV 기준)

| 데이터셋 | 모델 | ROC-AUC | PR-AUC | OOF Recall (큐) | OOF FPR (큐) |
|----------|------|---------|--------|-----------------|--------------|
| open (30건 사기 / 28,462행) | RF | 0.963 ± 0.044 | 0.789 ± 0.049 | 76.7% | 0.018% |
| IEEE-CIS (2,561건 / 100,000행) | RF | 0.893 ± 0.004 | 0.615 ± 0.010 | 52.3% | 0.47% |
| **합성 데이터** (495건 / 30,000행)† | **RF+LGBM** | **0.9999 ± 0.000** | **0.9997 ± 0.000** | **99.2%** | **0.020%** |

> **†합성 데이터 주의**: 사기 피처(V14, V12 등)에 의도적 이동(shift)을 적용했기 때문에 분류 난이도가 실제 데이터보다 낮습니다. 파이프라인 end-to-end 동작 검증 목적으로 사용하세요.
>
> **open 주의**: 단일 홀드아웃 ROC-AUC ≈ 0.9999는 홀드아웃 사기 6건에 의한 우연치로 신뢰할 수 없다. CV 결과를 기준으로 삼는다.

---

## 실험 스크립트 (비지도·하이브리드)

| 경로 | 내용 |
|------|------|
| `scripts/creditcard/if_unsupervised.py` | 비지도 전체: Part A/B/C |
| `scripts/creditcard/hybrid_if_rf.py` | IF 점수 + RF 결합 (홀드아웃) |
| `scripts/creditcard/hybrid_if_rf_cv.py` | IF 점수 + RF 결합 (5-fold CV, **권장**) |
| `scripts/open/supervised_rf.py` | open 데이터 지도 학습 + 제출 CSV |

```bash
# 빠른 실험 재현
python scripts/creditcard/hybrid_if_rf_cv.py
python scripts/open/supervised_rf.py
```

의존성: `pandas`, `scikit-learn`, `lightgbm`, `pyyaml`, `joblib`

---

## 테스트 실행

```bash
python -m pytest tests/ -v
```

---

## 보고서

| 파일 | 내용 |
|------|------|
| `docs/FRAUD_DETECTION_REPORT.md` | 기술·비즈니스 종합 보고서 |
| `docs/FDS_OPERATIONS_RUNBOOK_V1.md` | 운영 런북 |
| `docs/FDS_THESIS_SNIPPETS.md` | 논문용 문단 템플릿 |
| `docs/FDS_IEEE_CIS_CROSSWALK.md` | IEEE-CIS 실험 역할 구분 |
