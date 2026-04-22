# 스크립트 구조

| 폴더 | 데이터 | 목적 |
|------|--------|------|
| `creditcard/` | `data/creditcard.csv` (Kaggle) | 비지도·하이브리드 실험 |
| `open/` | `data/open/` (train/val/test) | 지도 학습·제출 파일 |
| `fds/` | `schemas/fds/*.yaml` + 라벨 CSV | 스키마 v1·RF 학습·배치 스코어(`transaction_id`, `score`, `reason_code`) |
| `ieee-cis/` | `data/ieee-cis/` (train_transaction·identity 등) | FDS·시간 검증·운영 임계값·walk-forward·IF 스윕 등 |

## `creditcard/` — Kaggle 신용카드

| 파일 | 하는 일 | 산출물 |
|------|---------|--------|
| `if_demo.py` | IF 한 번 전체 fit, 콘솔 요약만 (가장 가벼움) | 없음 |
| `if_holdout.py` | 홀드아웃 + contamination 스윕 + 하위 k% (중간) | 콘솔만 |
| `if_unsupervised.py` | Part A/B/C 전부, FPR·CSV·상위 K건 실험 (보고서용 메인) | `outputs/creditcard/if_eval_summary.csv` |
| `hybrid_if_rf.py` | IF 이상 점수 + RF/LGBM 지도 분류 결합 (홀드아웃) | `outputs/creditcard/hybrid_if_rf_compare.csv` |
| `hybrid_if_rf_cv.py` | 동일 파이프라인 **Stratified 5-fold CV** (권장 비교) | `outputs/creditcard/hybrid_if_rf_cv_compare.csv`, `outputs/creditcard/hybrid_if_recommendation.txt` |

## `open/` — 별도 과제 CSV

| 파일 | 하는 일 | 산출물 |
|------|---------|--------|
| `supervised_rf.py` | `val.csv`로 RF 학습·검증, `test.csv` 예측 | `data/open/submission_supervised*.csv` |

## `fds/` — 스키마 v1·의사결정·운영 프로토타입

| 파일 | 하는 일 | 산출물 |
|------|---------|--------|
| `train_export_rf.py` | YAML 스키마에 맞춰 RF+imputer 학습, joblib 번들 저장 | `outputs/fds/model_bundle_*.joblib` |
| `scoring.py` | `prepare_frame` 이후 스코어·`reason_code` (공용) | — |
| `batch_score.py` | CSV 스코어링만 | `score`, `reason_code` CSV |
| `rules_engine.py` | `policies/fds/rules_v1.yaml` 평가 | `rule_ids`, `rule_action` |
| `policy_merge.py` | 점수→밴드, 규칙+모델 조치 합성 | — |
| `batch_decide.py` | 스코어 + 임계값만 | `action`, `queue_priority` |
| `batch_run.py` | 규칙→모델→임계값 통합 | `final_action`, `audit_summary` 등 |
| `export_review_queue.py` | REVIEW(옵션 BLOCK) 추출·정렬·`--hash-id` | 검토 큐 CSV |
| `ops_benchmark.py` | 스코어링 처리량·ms/건 | 콘솔 |
| `ops_monitor.py` | 분포·승인율·(옵션) 라벨 품질 | JSON 요약 |
| `ops_drift.py` | 참조 vs 현재 특성 PSI·평균σ | JSON, `--fail-on-alert` |
| `ops_labeled_metrics.py` | 라벨 구간 ROC/PR-AUC 스냅샷·베이스라인 대비 | JSON |
| `schema.py` | 스키마 로드·별칭·합성 ID | — |
| `reason_codes.py` | 배치 내 \|z\|×중요도 상위 k 특성명 | — |

| `pipeline_open_standard.py` | val 홀드아웃 지표 → val 전체 번들 → test 전체 `batch_run`·큐·모니터·(옵션)드리프트 | `outputs/fds/README.md` 참고 |
| `build_mock_v2_dataset.py` | v2 모의 CSV 생성(합성 기본, `--from-val` 옵션) | `data/fds/mock_transactions_v2.csv` |
| `api_score_app.py` | FastAPI 준실시간 스코어 (`/v1/score/batch`) | `run_api.ps1` 또는 `cd scripts/fds` + uvicorn |
| `ops_shap_sample.py` | TreeExplainer SHAP 평균 절댓값 CSV | `requirements-fds-optional.txt` 필요 |

Windows 스케줄 예시: `scripts/fds/run_open_pipeline.ps1`. v2 모의: `docs/FDS_V2_MOCK.md`. API·SHAP: `requirements-fds-optional.txt`, `docs/FDS_OPERATIONS_RUNBOOK_V1.md` §5.

단위 테스트: `py -3 -m pytest tests/test_policy_merge.py -q`

정책·SLO: `policies/fds/thresholds_v1.yaml`, `rules_v1.yaml`, `ops_targets_v1.yaml`. 런북: `docs/FDS_OPERATIONS_RUNBOOK_V1.md`. 산출 요약: `outputs/fds/README.md`.

## `ieee-cis/` — IEEE-CIS Fraud Detection

| 파일 | 하는 일 | 산출물 |
|------|---------|--------|
| `fds.py` | 로드·identity 병합·전처리·`TransactionDT` 시간 순 분할 헬퍼 | 없음 |
| `baseline_rf.py` | FDS + RF stratified 홀드아웃 | `outputs/ieee_cis/baseline_rf_metrics.csv` |
| `time_split_rf.py` | `TransactionDT` 순 뒤 구간 검증 (운영·누수 검사에 가깝게) | `outputs/ieee_cis/time_split_rf_metrics.csv` |
| `hybrid_if_rf.py` | IF 이상 점수 + RF/LGBM (creditcard와 동일 아이디어, 원시 다특성) | `outputs/ieee_cis/hybrid_if_rf_compare.csv` |
| `feature_importance_rf.py` | RF `feature_importances_` + 전처리 후 컬럼명 (해석용) | `outputs/ieee_cis/rf_feature_importance.csv` |
| `time_split_hybrid_if_rf.py` | 시간 순 검증 + IF + RF/LGBM, 선택 `card1` 사전 집계 | `outputs/ieee_cis/time_split_hybrid_if_rf_compare.csv` |
| `eval_metrics.py` | 임계값 스윕·PR/캘리브 곡선 (다른 스크립트에서 import) | 없음 |
| `ieee_cis_operational_eval.py` | 시간 검증 + LGBM, Fβ·비용 임계값, PR/캘리브 CSV, 선택 보정·인코딩 | `outputs/ieee_cis/operational/` |
| `ieee_cis_walk_forward.py` | `TransactionDT` walk-forward 폴드 + LGBM | `outputs/ieee_cis/walk_forward/fold_metrics.csv` |
| `ieee_cis_if_sweep.py` | IF contamination 스윕·(선택) 수치 부분 IF·LOF | `outputs/ieee_cis/if_sweep/sweep_metrics.csv` |
| `ieee_cis_imbalance_compare.py` | `class_weight=balanced` vs `scale_pos_weight` | `outputs/ieee_cis/imbalance_compare/metrics.csv` |
| `time_split_blend_lgbm_rf.py` | 시간 검증 + LGBM·RF 확률 블렌딩 그리드 | `outputs/ieee_cis/time_split_blend_lgbm_rf_*.csv` |

산출물 분류는 `outputs/README.md` 참고. 상세 옵션은 `ieee-cis/README.md` 참고.

## 실행 (프로젝트 루트에서)

```text
py -3 scripts/creditcard/if_unsupervised.py
py -3 scripts/creditcard/hybrid_if_rf.py
py -3 scripts/creditcard/hybrid_if_rf_cv.py
py -3 scripts/open/supervised_rf.py
py -3 scripts/fds/pipeline_open_standard.py
py -3 scripts/fds/train_export_rf.py --schema schemas/fds/schema_v1_open.yaml --train-csv data/open/val.csv --holdout-fraction 0.2 --out outputs/fds/model_bundle_open_eval.joblib --metrics-out outputs/fds/metrics_open_val_holdout.json
py -3 scripts/fds/train_export_rf.py --schema schemas/fds/schema_v1_open.yaml --train-csv data/open/val.csv --out outputs/fds/model_bundle_open_full.joblib
py -3 scripts/fds/batch_score.py --bundle outputs/fds/model_bundle_open_full.joblib --input data/open/test.csv --output outputs/fds/scores_open_test.csv
py -3 scripts/fds/batch_decide.py --scores outputs/fds/scores_open_test.csv --output outputs/fds/decisions_open_test.csv
py -3 scripts/fds/batch_run.py --schema schemas/fds/schema_v1_open.yaml --input data/open/test.csv --bundle outputs/fds/model_bundle_open_full.joblib --output outputs/fds/decisions_full_pipeline.csv --nrows 5000
py -3 scripts/fds/export_review_queue.py --decisions outputs/fds/decisions_full_pipeline.csv --output outputs/fds/review_queue.csv --max-rows 200
py -3 scripts/fds/ops_monitor.py --decisions outputs/fds/decisions_full_pipeline.csv --json-out outputs/fds/monitor_summary.json
py -3 scripts/fds/ops_benchmark.py --schema schemas/fds/schema_v1_open.yaml --input data/open/test.csv --bundle outputs/fds/model_bundle_open_full.joblib --nrows 10000
py -3 scripts/fds/ops_drift.py --ref data/open/train.csv --current data/open/test.csv --ref-nrows 8000 --current-nrows 8000
py -3 scripts/fds/ops_labeled_metrics.py --schema schemas/fds/schema_v1_open.yaml --input data/open/val.csv --bundle outputs/fds/model_bundle_open_eval.joblib --json-out outputs/fds/metrics_baseline.json
py -3 scripts/ieee-cis/baseline_rf.py
py -3 scripts/ieee-cis/time_split_rf.py
py -3 scripts/ieee-cis/hybrid_if_rf.py
py -3 scripts/ieee-cis/feature_importance_rf.py
py -3 scripts/ieee-cis/time_split_hybrid_if_rf.py
py -3 scripts/ieee-cis/ieee_cis_operational_eval.py
py -3 scripts/ieee-cis/ieee_cis_walk_forward.py
py -3 scripts/ieee-cis/ieee_cis_if_sweep.py
py -3 scripts/ieee-cis/ieee_cis_imbalance_compare.py
py -3 scripts/ieee-cis/time_split_blend_lgbm_rf.py
```

open FDS의 **정직한 검증 수치**는 `outputs/fds/metrics_open_val_holdout.json`(파이프라인 1단계)을 우선한다. `ops_labeled_metrics`는 학습 데이터와 겹치지 않는 라벨 CSV가 있을 때 보조로 쓴다.

이전 경로와의 대응:

- `creditcard_if_unsupervised.py` → `creditcard/if_unsupervised.py`
- `creditcard_if_holdout.py` → `creditcard/if_holdout.py`
- `creditcard_if_demo.py` → `creditcard/if_demo.py`
- `creditcard_hybrid_if_rf.py` → `creditcard/hybrid_if_rf.py`
- `open_supervised_rf.py` → `open/supervised_rf.py`
