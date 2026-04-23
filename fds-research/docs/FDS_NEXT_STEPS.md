# FDS 다음 단계 가이드

**역할**: 지금 레포에 있는 구현(배치 스코어·규칙·운영 스크립트) **이후**에 무엇을 하면 되는지 **순서·판단 기준**만 모은 문서.  
**이미 정리된 곳**: 범위·성공 정의 → `FDS_SCOPE_AND_SUCCESS_V1.md`, 명령·SLO → `FDS_OPERATIONS_RUNBOOK_V1.md`, 산출물 이름 → `outputs/fds/README.md`, 스크립트 표 → `scripts/README.md`.

## 진행 상황 (레포 기준 — 단계별 산출 연결)

| 구간 | 상태 |
|------|------|
| A1 | §2.3 초안 목표 + §2.4 스냅샷 — 팀 최종 합의만 남음 |
| A2·A3·A4 | 보고서 **복붙용** `docs/FDS_THESIS_SNIPPETS.md`, §2.5 드리프트 문장 |
| B | v2 모의: `FDS_V2_MOCK.md`, `schema_v2_open_mock.yaml`, `mock_transactions_v2.csv`, `rules_v2_mock.yaml` |
| C1 | `scripts/fds/run_open_pipeline.ps1` |
| C2 | `docs/FDS_OUTPUT_RETENTION.md` |
| C3 | `ops_targets_v1.yaml`의 `observed_reference` + 기존 임계 (환경별 수정) |
| D1 | `scripts/fds/api_score_app.py`, `run_api.ps1`, `requirements-fds-optional.txt` |
| D2 | `scripts/fds/ops_shap_sample.py` (shap 설치 후) |
| D3 | `docs/FDS_IEEE_CIS_CROSSWALK.md` |
| 테스트 | `tests/test_policy_merge.py` |

**남는 인간 작업**: 팀·지도와 §2.3 숫자 확정, 보고서에 스니펫 반영·다듬기, 운영 환경에 맞는 스케줄·비밀·권한 설정.

---

## A. 비즈니스·보고 (가장 먼저)

| 순서 | 할 일 | 완료 기준 |
|------|--------|-----------|
| A1 | §2.3 **목표 숫자** 합의(큐 상한·Recall·FPR 등) | `FDS_SCOPE_AND_SUCCESS_V1.md` 표에 기입 |
| A2 | §2.4 스냅샷과 **같은 용어**로 보고서에 쓰기 | “검증(홀드아웃 JSON)” vs “운영 요약(모니터 JSON·무 라벨)” 구분 |
| A3 | 홀드아웃 **사기 건수 소표본** 한계를 보고서에 한 문장 | `metrics_open_val_holdout.json` 인용 시 필수 |
| A4 | 드리프트 알람 컬럼이 있으면 **해석** 한 줄 | `drift_train_vs_test.json` 등 |

---

## B. 데이터·스키마 (현실화)

| 순서 | 할 일 | 완료 기준 |
|------|--------|-----------|
| B1 | 모의 **스키마 v2** 컬럼 목록 확정 | `channel`, `country_txn` 등 — `fraud_dataset_schema_reference.md`와 맞춤 |
| B2 | 소량 **모의 CSV** 1개 + 스키마 YAML 1개 | `batch_run`까지 통과 |
| B3 | 규칙 YAML에 실제 컬럼 연결 | `rules_v1.yaml` 패턴 복제 |

---

## C. 운영·자동화 (선택)

| 순서 | 할 일 | 완료 기준 |
|------|--------|-----------|
| C1 | 야간/정기 **배치 명령 한 줄** 문서화 | 스케줄러에 그대로 넣을 수 있는 커맨드 |
| C2 | 산출물 보관 위치·**보존 기간** | 로그·JSON·(필요 시) CSV 정책 |
| C3 | `ops_targets_v1.yaml` 수치를 **환경에 맞게** 조정 | 지연·PSI·AUC 드롭 임계 |

---

## D. 기술 심화 (시간 남을 때)

| 순서 | 할 일 | 비고 |
|------|--------|------|
| D1 | 준실시간 **스코어 API** 초안 | FastAPI 등 단일 엔드포인트 |
| D2 | 설명 가능성 **범위 정한 뒤** SHAP 샘플 | 의존성·지연 증가 |
| D3 | IEEE-CIS 등 **별도 데이터**와 동일 파이프라인 비교 | 연구 확장 |

---

## 빠른 참조: 지금 당장 열어볼 파일

1. `docs/FDS_SCOPE_AND_SUCCESS_V1.md` — §2.3·§2.4  
2. `outputs/fds/metrics_open_val_holdout.json` — 검증 수치  
3. `outputs/fds/monitor_open_test_full.json` — test 운영 요약(파이프라인 실행 후)  
4. `policies/fds/thresholds_v1.yaml` — 임계값 튜닝 시 수정  

표준 재실행:

```text
py -3 scripts/fds/pipeline_open_standard.py
```

---

## 문서 맵

```text
FDS_SCOPE_AND_SUCCESS_V1.md   → 무엇을 맞추면 성공인지 + 구현 색인
FDS_OPERATIONS_RUNBOOK_V1.md  → 스크립트·SLO·드리프트 절차
FDS_NEXT_STEPS.md             → 본 문서 (이후 로드맵)
FDS_V2_MOCK.md                → 스키마 v2 모의·명령
FDS_OUTPUT_RETENTION.md       → 산출물 보존 템플릿
FDS_THESIS_SNIPPETS.md        → 보고서 문단(A2·A3·A4)
FDS_IEEE_CIS_CROSSWALK.md     → IEEE-CIS 실험과 역할 구분
outputs/fds/README.md         → 산출 파일 의미
```
