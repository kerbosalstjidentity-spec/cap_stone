# IEEE-CIS 실험과 FDS 배치 파이프라인 연계 (D3)

같은 **“규칙·모델·임계값·모니터링”** 아이디어를, 데이터가 다른 두 축에서 다룬다.

| 개념 | `data/open/` + `scripts/fds/` | `data/ieee-cis/` + `scripts/ieee-cis/` |
|------|-------------------------------|----------------------------------------|
| 스키마·로드 | `schemas/fds/schema_v1_open.yaml`, `schema.py` | `fds.py` (TransactionID, TransactionDT, 병합) |
| 지도 학습·번들 | `train_export_rf.py` | `baseline_rf.py`, `time_split_rf.py`, `ieee_cis_operational_eval.py` 등 |
| 시간 순 검증 | 홀드아웃은 **무작위 stratified** (open val) | **TransactionDT** 기준 분할·walk-forward |
| 운영 임계값·비용 | `thresholds_v1.yaml`, `batch_decide.py` | `eval_metrics.py`, `ieee_cis_operational_eval.py` |
| 블렌딩·LGBM | (RF 중심 프로토타입) | `time_split_blend_lgbm_rf.py` |

**보고서에서 쓰는 말**: open FDS 파이프라인은 **제출용 CSV·경량 스키마**에 맞춘 **운영 프로토타입**이고, IEEE-CIS 스크립트는 **다특성·시간축**에서 동일한 의사결정 문제를 **연구 깊이**로 보완한다. 숫자를 서로 직접 비교하지 않는다.
