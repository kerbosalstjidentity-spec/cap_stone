# FDS 운영 준비 런북 (v1)

캡스톤 로드맵 **3. 의사결정 레이어**, **4. 운영 준비**에 대응하는 **실행 가능한 스크립트·설정**을 한곳에 정리한다.  
수치 목표는 `policies/fds/ops_targets_v1.yaml`에서 조정한다.

## open 데이터 표준 일괄 실행

```text
py -3 scripts/fds/pipeline_open_standard.py
```

산출·의미는 `outputs/fds/README.md` 참고. **그다음에 할 일**은 `docs/FDS_NEXT_STEPS.md`.  
Windows 정기 실행 예시: `scripts/fds/run_open_pipeline.ps1`. 산출 보존: `docs/FDS_OUTPUT_RETENTION.md`.

---

## 3. 의사결정 레이어

| 구성요소 | 구현 | 설명 |
|----------|------|------|
| 규칙 선행 | `policies/fds/rules_v1.yaml` + `scripts/fds/rules_engine.py` | 블록리스트 파일·금액·`column_in_values`(국가 코드 등). 컬럼 없으면 `skip_if_missing_column` / `skip_if_no_amount` 로 스킵. |
| 모델 점수 | `train_export_rf.py` 번들 + `scoring.py` | 사기 확률·`reason_code`. |
| 임계값 밴드 | `policies/fds/thresholds_v1.yaml` | `review_min` ~ `block_min` 구간. |
| 합성 정책 | `policy_merge.py` + `batch_run.py` | `final_action = max_severity(rule_action, model_action)`. |
| 검토 큐 | `export_review_queue.py` | `REVIEW`만(옵션 `BLOCK` 포함), `queue_priority` 정렬, `--hash-id`로 로그 PII 완화. |

**국가·카테고리 예시 (`rules_v1.yaml`의 `rules`에 추가)** — 스키마에 `country_txn` 등 컬럼이 있을 때만 적용됨.

```yaml
  - id: R_COUNTRY_REVIEW
    action: REVIEW
    column_in_values:
      column: country_txn
      values: ["AA", "BB"]
    skip_if_missing_column: true
```

**통합 배치 (권장 단일 진입점)**

```text
py -3 scripts/fds/batch_run.py --schema schemas/fds/schema_v1_open.yaml --input data/open/test.csv --bundle outputs/fds/model_bundle_open_full.joblib --output outputs/fds/decisions_full_pipeline.csv
```

**검토 큐 추출**

```text
py -3 scripts/fds/export_review_queue.py --decisions outputs/fds/decisions_full_pipeline.csv --output outputs/fds/review_queue.csv --max-rows 500
```

---

## 4. 운영 준비

### 4.1 지연·처리량

- 스크립트: `scripts/fds/ops_benchmark.py`  
- 산출: 구간 벽시계 기준 `throughput_rps`, `ms_per_row` (단일 프로세스·배치).  
- `ops_targets_v1.yaml`의 `latency`와 비교해 **대략적** SLO 점검 (p99는 반복 측정·부하 도구로 별도 확정).

```text
py -3 scripts/fds/ops_benchmark.py --schema schemas/fds/schema_v1_open.yaml --input data/open/test.csv --bundle outputs/fds/model_bundle_open_full.joblib --nrows 20000
```

### 4.2 모니터링 (분포·승인율·큐 품질)

- 스크립트: `scripts/fds/ops_monitor.py`  
- 점수 분위수, `PASS` 비율(승인 프록시), 동일 CSV에 라벨 컬럼이 있으면 검토+차단 구간 내 사기 비율·TP/FP/FN 요약.

```text
py -3 scripts/fds/ops_monitor.py --decisions outputs/fds/decisions_full_pipeline.csv --json-out outputs/fds/monitor_summary.json
```

라벨이 붙은 통합 파일이 있으면:

```text
py -3 scripts/fds/ops_monitor.py --decisions path/to/merged.csv --label-col Class
```

**라벨 지연**: 실제 운영에서는 거래 시점과 `label_ts`가 어긋난다. 주기 배치로 “확정 라벨이 붙은 구간”만 잘라 위 스크립트를 돌리고, 기준 시각을 런북·보고서에 명시한다.

### 4.3 드리프트

**특성 분포 (PSI·평균 σ)**

```text
py -3 scripts/fds/ops_drift.py --ref data/open/train.csv --current data/open/test.csv --ref-nrows 15000 --current-nrows 15000 --json-out outputs/fds/drift_features.json
```

`ops_targets_v1.yaml`의 `monitoring.score_distribution_shift_psi_alert`, `mean_shift_sigma_alert`와 비교. CI에서 쓰려면 `--fail-on-alert`.

**모델 성능 (AUC·PR-AUC) — 라벨 구간 스냅샷**

```text
py -3 scripts/fds/ops_labeled_metrics.py --schema schemas/fds/schema_v1_open.yaml --input data/open/val.csv --bundle outputs/fds/model_bundle_open_eval.joblib --json-out outputs/fds/metrics_baseline.json
```

**주의**: `model_bundle_open_full.joblib`(val 전체 학습)로 **같은 val**을 다시 스코어하면 AUC가 비현실적으로 높다. 정직한 지표는 `metrics_open_val_holdout.json`(홀드아웃) 또는 **eval 번들**(`model_bundle_open_eval.joblib`)과 **겹치지 않는** 라벨 CSV 조합으로 잰다.

이후 주기 실행 시 동일 옵션에 `--baseline-json outputs/fds/metrics_baseline.json`을 주고, `drift.auc_drop_alert` 등 초과 시 `--fail-on-alert`.

### 4.4 감사·설명

- **모델**: `reason_code`(상위 특성명), `audit_summary`(`batch_run` 산출).  
- **규칙**: `rule_ids`.  
- **SHAP** 샘플 스크립트: `scripts/fds/ops_shap_sample.py` (`requirements-fds-optional.txt`). 운영 전 구간·샘플 크기를 제한할 것.

### 4.5 보안·개인정보

- 로그·검토 큐에는 필드 최소화; `export_review_queue.py --hash-id` 참고.  
- 블록리스트·원본 ID 파일은 권한·암호화 정책에 따름. 예시: `data/fds/blocklist_transaction_ids.example.txt`.

---

## 파일·정책 경로 요약

| 경로 | 용도 |
|------|------|
| `policies/fds/rules_v1.yaml` | 규칙 정의 |
| `policies/fds/thresholds_v1.yaml` | 점수 밴드 |
| `policies/fds/ops_targets_v1.yaml` | SLO·알람 임계 |
| `data/fds/blocklist_transaction_ids.example.txt` | 블록리스트 예시 |
| `docs/FDS_SCOPE_AND_SUCCESS_V1.md` | 범위·성공 기준·프로토타입 색인 |

---

## 5. 준실시간 API·SHAP (선택, D1·D2)

의존성:

```text
pip install -r requirements-fds-optional.txt
```

**API (FastAPI)**

- 기동: `scripts/fds/run_api.ps1` 또는 `cd scripts/fds` 후  
  `py -3 -m uvicorn api_score_app:app --host 127.0.0.1 --port 8765`
- 번들 경로: 환경변수 `FDS_BUNDLE_PATH` (미설정 시 `outputs/fds/model_bundle_open_full.joblib`)
- `GET /health`, `POST /v1/score/batch` (본문: `{ "V1": …, "V2": …, … }` 객체의 배열; `ID` 선택)

**SHAP (소량 행)**

```text
py -3 scripts/fds/ops_shap_sample.py --bundle outputs/fds/model_bundle_open_full.joblib --input data/fds/mock_transactions_v2.csv --nrows 100
```

산출: `outputs/fds/shap_mean_abs_sample.csv` (gitignore 대상 CSV이므로 로컬 생성).

---

## 6. 연구 확장·IEEE-CIS (참고, D3)

앙상블·블렌딩·실제 라벨 정의는 `scripts/ieee-cis/` 및 `docs/FRAUD_DETECTION_REPORT.md`를 따른다. **open FDS와의 역할 구분**은 `docs/FDS_IEEE_CIS_CROSSWALK.md` 참고. 본 런북은 **배치 FDS 루프**에 초점을 둔다.
