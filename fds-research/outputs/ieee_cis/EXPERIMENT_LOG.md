# IEEE-CIS 실험 기록 (산출물 요약)

프로젝트 루트에서 실행한 IEEE-CIS 스크립트 결과를 한곳에 모은 표입니다.  
세부 수치는 각 CSV·JSON을 기준으로 합니다. (모든 경로는 `outputs/ieee_cis/` 기준 상대)

## 1. 단일 분할·베이스라인

| 산출 파일 | 설정 요약 | ROC-AUC | PR-AUC |
|-----------|-----------|---------|--------|
| `baseline_rf_metrics.csv` | stratified 홀드아웃, RF, identity | 0.9384 | 0.7291 |
| `time_split_rf_metrics.csv` | 시간 순 검증 25%, RF, identity | 0.8953 | 0.5134 |
| `hybrid_if_rf_compare.csv` | stratified + IF + RF/LGBM (실행 시점·표본에 따라 변동) | (파일 참고) | (파일 참고) |
| `time_split_hybrid_if_rf_compare.csv` | 시간 검증 + IF + RF/LGBM, 전체 행 | (파일 참고) | (파일 참고) |

## 2. 운영 평가 (`operational/`)

**마지막 저장:** `operational/run_meta.json` 기준 — LGBM + extended priors + 빈도 인코딩 + **isotonic 보정**.

| 항목 | 값 |
|------|-----|
| ROC-AUC | 0.8883 |
| PR-AUC | 0.4739 |

**참고:** 보정 **없이** 돌린 적이 있으며, 그때 ROC-AUC ≈ **0.8987**, PR-AUC ≈ **0.5049** (`operational/run_meta_uncalibrated.json`).

**같은 폴더:** `threshold_scan_detail.csv`, `threshold_scan_summary.csv`, `pr_curve.csv`, `calibration_curve.csv`

## 3. Walk-forward

| 파일 | 내용 |
|------|------|
| `walk_forward/fold_metrics.csv` | 4 folds, extended priors, LGBM |

## 4. 불균형 비교

| 파일 | 내용 |
|------|------|
| `imbalance_compare/metrics.csv` | `balanced` vs `scale_pos_weight` |

## 5. LGBM·RF 확률 블렌딩 (시간 검증)

| 파일 | 내용 |
|------|------|
| `time_split_blend_lgbm_rf_grid.csv` | w별 ROC/PR |
| `time_split_blend_lgbm_rf_summary.csv` | 단독 지표 + 최적 w |

스크립트: `scripts/ieee-cis/time_split_blend_lgbm_rf.py`

## 6. IF·LOF 스윕

| 파일 | 내용 |
|------|------|
| `if_sweep/sweep_metrics.csv` | contamination 스윕 + LOF (랜덤 분할 실험 시 주의) |

## 7. 특성 중요도

| 파일 | 내용 |
|------|------|
| `rf_feature_importance.csv` | RF 상위 특성 |

---

갱신: 실험 후 요약용으로 수동·반자동 정리.
