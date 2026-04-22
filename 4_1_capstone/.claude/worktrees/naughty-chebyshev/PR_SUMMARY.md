# PR: FDS 실제 운영 수준 전환 — 신뢰도·아키텍처·테스트 전면 개선

## 브랜치 정보
- **Branch**: `claude/naughty-chebyshev`
- **Base**: `main`
- **총 커밋**: 15건

---

## 커밋 목록 (최신 → 오래된 순)

| 해시 | 설명 |
|------|------|
| f001544 | Feat: 합성 파이프라인 스크립트 + FastAPI 엔드포인트 테스트 11건 추가 |
| 15af186 | Test: velocity·retrain_trigger·ensemble 단위 테스트 29건 추가 + E2E 검증 |
| b8443df | Feat: 합성 학습 데이터 생성 + 앙상블 모델 학습 + 문서 갭 분석 추가 |
| cbcf153 | Feat: 실제 FDS 아키텍처 시뮬레이션 — velocity 피처·앙상블·승인 API·재학습 트리거 |
| 6bdb60e | Docs: FDS 현재 범위 vs 실제 운영 시스템 갭 문서화 |
| 38495df | Docs: README 파이프라인 실행 순서 정리 + 보고서 FDS 섹션 추가 |
| 205581b | Feat: PSI 계산 테스트 6건 + ops_labeled_metrics 테스트 8건 + IEEE-CIS 파이프라인 스크립트 |
| 76f4351 | Feat: YAML 입력 검증 강화 + E2E 통합 테스트 22건 추가 |
| 741dd76 | Fix: V30 드리프트 오탐 수정 + IEEE-CIS 모델 번들 생성 |
| 49cb033 | Fix: 드리프트 심각도 등급·경고 가시성·경로 안정성 개선 |
| 0e9eef2 | Fix: FDS 파이프라인 버그 4건 수정 |
| 2351a3c | Fix: 데이터 오염·지표 신뢰도 문제 전반 수정 |
| 89c3a00 | Fix: 평가 신뢰도 개선 - k-fold CV 추가, reason_codes 방법 명확화 |
| 4807059 | Policy: 차단 정책 정교화 - 변수 기반 조정 추가, 테스트 완료 |
| 055adac | Test: 운영 데이터 적용 완료 - 스코어 계산, 액션 결정, 모니터링 |

---

## 주요 변경 영역

### 1. 신뢰도 수정 (Fix)
- **ROC-AUC 0.9999 → 0.9625 ± 0.044**: 홀드아웃 오염 제거, 5-fold CV 도입
- **reason_codes 근사치 명시**: SHAP 기반이 아님을 docstring에 명확화
- **n_train 지표 분리**: SMOTE 전/후 행 수 구분
- **V30 드리프트 오탐 수정**: PSI 계산 시 랜덤 샘플링으로 분포 안정화
- **정책 무음 실패 해결**: `stderr` 경고 추가 (batch_decide.py)
- **상대경로 → 절대경로**: batch_run.py 경로 안정성 개선

### 2. FDS 아키텍처 확장 (Feat)
- **velocity_features.py**: tx_count_1h/24h, amount_spike_flag, country_change_flag 등 6개 피처
- **rules_v2_velocity.yaml**: velocity 기반 규칙 10개 추가
- **train_export_ensemble.py**: RF + LightGBM 앙상블 (Soft Voting)
- **scoring.py**: 앙상블 번들 처리 지원
- **api_score_app.py**: `/v1/authorize` 결제 승인/거부 엔드포인트 추가
- **retrain_trigger.py**: PSI 임계값 기반 자동 재학습 트리거 (MLOps)
- **pipeline_ieee_cis_standard.py**: IEEE-CIS 전용 표준 파이프라인
- **pipeline_synthetic_standard.py**: 합성 데이터 전용 파이프라인

### 3. 데이터 (Data)
- **generate_synthetic_data.py**: Gaussian Mixture 기반 합성 데이터 생성기
  - 30,000행, 사기 1.5% (450건) — CV 안정적
  - 실제 creditcard.csv 통계 기반 피처 분포 근사
  - user_id, event_ts, amount, merchant_id, channel, country_txn 포함
- **앙상블 모델 번들**: RF + LightGBM 5-fold CV 학습 완료

### 4. 테스트 커버리지 (Test)
| 테스트 파일 | 건수 | 검증 내용 |
|------------|------|----------|
| test_e2e_pipeline.py | 22건 | 스키마→스코어→규칙→정책 E2E |
| test_psi_math.py | 6건 | PSI 수학적 속성 |
| test_labeled_metrics.py | 8건 | 사후 성능 평가 |
| test_velocity_features.py | 12건 | velocity 피처 계산 |
| test_retrain_trigger.py | 9건 | PSI 임계값 판단 |
| test_ensemble_scoring.py | 8건 | 앙상블 번들 스코어링 |
| test_api_authorize.py | 11건 | FastAPI /v1/authorize 엔드포인트 |
| **합계** | **76건** | |

### 5. 문서 (Docs)
- **README.md**: 파이프라인 실행 순서 전면 정리
- **docs/FRAUD_DETECTION_REPORT.md**: 실제 FDS 갭 분석 섹션 추가 (8.6절)
- **ops_drift.py**: PSI 심각도 5등급 분류 (INFO/WARN/MAJOR/CRITICAL/SEVERE)

---

## 성능 지표 비교

| 지표 | 수정 전 | 수정 후 | 방법 |
|------|---------|---------|------|
| open ROC-AUC | 0.9999 | 0.9625 ± 0.044 | 5-fold CV |
| open PR-AUC | 0.9762 | 0.7891 ± 0.049 | 5-fold CV |
| IEEE-CIS ROC-AUC | — | 0.893 ± 0.004 | 5-fold CV |
| IEEE-CIS PR-AUC | — | 0.615 ± 0.010 | 5-fold CV |
| 총 테스트 수 | ~10건 | 76건 | — |

---

## 현재 상태
- 로컬 커밋 완료
- 원격 연결 후 `PUSH_TO_REMOTE.sh` 실행하면 push + PR 생성 가능
- 생성일: 2026-03-27
