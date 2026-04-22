# IEEE-CIS (`data/ieee-cis/`)

Kaggle IEEE-CIS Fraud Detection 원본 CSV용 스크립트입니다.  
`creditcard/`·`open/`과 **경로·스키마가 다르므로** 이 폴더만 사용합니다.

## 폴더·산출 정리

| 위치 | 역할 |
|------|------|
| `scripts/ieee-cis/` | 실험 스크립트. |
| `outputs/creditcard/` | Kaggle creditcard 비지도·하이브리드 CSV (이 폴더 스크립트 아님). |
| `outputs/ieee_cis/` | IEEE-CIS 산출 **전부**: 메트릭 CSV, `EXPERIMENT_LOG.md`, `operational/`·`walk_forward/`·`if_sweep/`·`imbalance_compare/`. |
| `outputs/README.md` | `creditcard` vs `ieee_cis` 분류 설명. |
| `data/ieee-cis/` | Kaggle CSV는 **Git 제외** (`README.txt` 참고). |

**앙상블 결정용 최소 실험:** `time_split_blend_lgbm_rf.py` → `outputs/ieee_cis/time_split_blend_lgbm_rf_*.csv`.

## creditcard 대비 확장 축

| 축 | 설명 |
|----|------|
| **시간 순 검증** | `TransactionDT`로 앞·뒤 구간 분리 (`time_split_rf.py`, `time_split_hybrid_if_rf.py`). |
| **Walk-forward** | 시간 분위별 검증 구간을 순차 적용 (`ieee_cis_walk_forward.py`, `fds.walk_forward_time_splits`). |
| **identity·집계** | `train_identity` 병합; `add_extended_prior_features`로 card/addr/이메일/Device **이전 건수·누적 금액**. |
| **인코딩** | `apply_frequency_encoding`, `apply_target_encoding_cv` (학습만 fit, 검증은 동일 규칙). |
| **운영 평가** | Fβ·비용(fp·fn)·재현율 하한 기준 임계값, PR/캘리브레이션 곡선 (`ieee_cis_operational_eval.py`, `eval_metrics.py`). |
| **IF·LOF 실험** | contamination 스윕, 수치 일부만 IF, LOF+지도 (`ieee_cis_if_sweep.py`). |
| **불균형** | `balanced` vs `scale_pos_weight` (`ieee_cis_imbalance_compare.py`). |
| **블렌딩** | 시간 검증 + LGBM·RF 확률 가중 (`time_split_blend_lgbm_rf.py`). |

## 누수·시간 (점검 메모)

- **`D*`, `TransactionDT`**: 대회 논의 자료 기준, 일부 `D`는 “이전 이벤트로부터 경과” 등 **시간 차** 의미가 있어, **미래 라벨은 쓰지 않아도** 분포 이동이 클 수 있음. 시간 검증에서 성능이 떨어지는 것은 이 영향일 수 있음.
- **집계 특성**(`add_*_prior_*`): 같은 `TransactionDT` 순에서 **과거 행만** 누적하므로, 검증 시점 기준으로는 미래 거래 정보를 쓰지 않음.
- **빈도·타깃 인코딩**: 학습 분할에서만 통계 추정, 검증·미래 구간에는 **학습에서 본 map / TargetEncoder 규칙**만 적용. 동일 컬럼에 빈도+타깃 인코딩을 동시에 쓰면 중복·다중공선 가능 → 보통 하나만 선택.

**Focal loss** 등은 별도 딥러닝·추가 라이브러리가 필요해 이 레포에는 넣지 않았습니다.

## FDS (`fds.py`)

- `IeeeCisFDS`, `make_preprocessor`, `split_train_val_by_time`
- `walk_forward_time_splits(df, n_folds=...)`
- `add_extended_prior_features` / `add_card1_prior_features` (하위 호환)
- `apply_frequency_encoding`, `apply_target_encoding_cv`

## 실험 요약 로그

- `outputs/ieee_cis/EXPERIMENT_LOG.md` — 주요 CSV·지표 요약.
- `outputs/ieee_cis/operational/run_meta.json` — 마지막 운영 평가 메타.
- `outputs/ieee_cis/operational/run_meta_uncalibrated.json` — 보정 없이 돌렸을 때 ROC/PR.

## 산출물 요약 (`outputs/ieee_cis/`)

| 경로 |
|------|
| `baseline_rf_metrics.csv`, `time_split_rf_metrics.csv`, `hybrid_if_rf_compare.csv`, … |
| `time_split_hybrid_if_rf_compare.csv`, `rf_feature_importance.csv` |
| `operational/`, `walk_forward/`, `if_sweep/`, `imbalance_compare/` |
| `time_split_blend_lgbm_rf_grid.csv`, `time_split_blend_lgbm_rf_summary.csv` |

## 실행 예 (프로젝트 루트)

```text
py -3 scripts/ieee-cis/baseline_rf.py
py -3 scripts/ieee-cis/ieee_cis_operational_eval.py --extended-priors --freq-encode-cols "ProductCD,P_emaildomain"
py -3 scripts/ieee-cis/ieee_cis_operational_eval.py --calibrate isotonic --scale-pos-weight
py -3 scripts/ieee-cis/ieee_cis_walk_forward.py --n-folds 4
py -3 scripts/ieee-cis/ieee_cis_if_sweep.py --max-rows 80000 --if-numeric-only 80
py -3 scripts/ieee-cis/ieee_cis_imbalance_compare.py
py -3 scripts/ieee-cis/time_split_blend_lgbm_rf.py
py -3 scripts/ieee-cis/time_split_blend_lgbm_rf.py --extended-priors
```

개발용 `--max-rows N` 은 대부분의 스크립트에서 공통으로 지원합니다.
