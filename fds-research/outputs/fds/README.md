# FDS 배치 산출물 (`outputs/fds/`)

## 한 번에 돌리기 (권장)

프로젝트 루트에서:

```text
py -3 scripts/fds/pipeline_open_standard.py
```

옵션: `--holdout 0.2`(기본), `--skip-drift`, `--drift-ref-nrows 20000`.

## 주요 파일

| 파일 | 설명 |
|------|------|
| `metrics_open_val_holdout.json` | `val.csv` **stratified 홀드아웃**만으로 학습한 번들의 검증 지표(ROC/PR-AUC, 임계값 기준 큐 크기·Recall·FPR). **정직한 모델 평가**는 이 파일을 인용. |
| `model_bundle_open_eval.joblib` | 위 홀드아웃 학습 전용 번들(평가·비교용). |
| `model_bundle_open_full.joblib` | `val.csv` **전체** 학습 번들 — **test 스코어링**에 사용. |
| `decisions_open_test_full.csv` | `test.csv` 전체에 대한 `batch_run` 결과. |
| `review_queue_open_test_full.csv` | `REVIEW`만 추출·우선순위 정렬. |
| `monitor_open_test_full.json` | 점수 분위·조치 비율 등 요약. |
| `drift_train_vs_test.json` | train vs test(각 상위 N행) 특성 PSI·σ (샘플 한도는 파이프라인 옵션). |

## 재현 시 유의

- **평가**: `metrics_open_val_holdout.json` ≠ `model_bundle_open_full`로 test를 찍은 뒤의 라벨 없는 지표.
- **임계값**: `policies/fds/thresholds_v1.yaml` 변경 시 홀드아웃 정책 지표도 함께 변함.
- 구버전 산출: `model_bundle_open.joblib` 등 이전 실험 파일이 있으면 혼동하지 않도록 위 표준 파일명을 우선한다.
