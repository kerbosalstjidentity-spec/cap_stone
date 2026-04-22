# 스키마 v2 모의 (channel·country_txn)

## 목적

`FDS_NEXT_STEPS.md` **B단계** 착수: 모델 특성은 **V1–V30 유지**, 규칙·감사를 위해 **메타 컬럼**을 CSV에 추가한다.

## 파일

| 파일 | 설명 |
|------|------|
| `schemas/fds/schema_v2_open_mock.yaml` | v1과 동일 특성 목록 + 문서 필드 `metadata_for_rules_optional` |
| `data/fds/mock_transactions_v2.csv` | `build_mock_v2_dataset.py`로 생성(기본: 합성, val 없이 재현 가능) |
| `policies/fds/rules_v2_mock.yaml` | `country_txn == HIGH_RISK` → REVIEW 등 |

## 생성

```text
py -3 scripts/fds/build_mock_v2_dataset.py
py -3 scripts/fds/build_mock_v2_dataset.py --from-val --nrows 600
```

## 스코어·결정 (번들 필요)

`model_bundle_open_full.joblib` 등 V1–V30 번들과 호환된다.

```text
py -3 scripts/fds/batch_run.py --schema schemas/fds/schema_v2_open_mock.yaml --input data/fds/mock_transactions_v2.csv --bundle outputs/fds/model_bundle_open_full.joblib --rules policies/fds/rules_v2_mock.yaml --output outputs/fds/decisions_mock_v2.csv
```

번들이 없으면 먼저 `py -3 scripts/fds/pipeline_open_standard.py` 또는 `train_export_rf.py`로 생성한다.
