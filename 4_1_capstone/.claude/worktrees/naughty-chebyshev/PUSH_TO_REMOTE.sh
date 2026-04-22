#!/bin/bash
# 원격에 연결되면 실행할 명령어들

# 1. 원격 브랜치 푸시
git push -u origin claude/naughty-chebyshev

# 2. PR 생성
gh pr create \
  --title "Feat: FDS 실제 운영 수준 전환 — 신뢰도·아키텍처·테스트 전면 개선" \
  --body "$(cat <<'EOF'
## 요약

FDS 파이프라인을 단순 ML 실험 수준에서 실제 운영 수준 아키텍처로 전환.
평가 신뢰도 수정, 실시간 피처 엔지니어링, 앙상블 모델, 결제 승인 API, MLOps 재학습 트리거, 합성 데이터, 테스트 76건 추가.

## 주요 변경사항

### 신뢰도 수정
- ROC-AUC 0.9999 → 0.9625 ± 0.044 (홀드아웃 오염 제거, 5-fold CV 도입)
- reason_codes 근사치 명시 (SHAP 아님)
- V30 드리프트 오탐 수정
- 정책 무음 실패 해결 (stderr 경고)

### FDS 아키텍처 확장
- `velocity_features.py`: tx_count_1h/24h, amount_spike_flag, country_change_flag
- `rules_v2_velocity.yaml`: velocity 기반 규칙 10개
- `train_export_ensemble.py`: RF + LightGBM Soft Voting 앙상블
- `api_score_app.py`: `/v1/authorize` 결제 승인/거부 엔드포인트
- `retrain_trigger.py`: PSI 임계값 기반 자동 재학습 트리거
- `pipeline_ieee_cis_standard.py`, `pipeline_synthetic_standard.py`

### 데이터
- `generate_synthetic_data.py`: 30,000행 합성 데이터 (사기 1.5%, CV 안정적)
- user_id, event_ts, amount, merchant_id 포함 → velocity 피처 테스트 가능

### 테스트 (76건)
- E2E 파이프라인 22건
- PSI 수학 속성 6건
- ops_labeled_metrics 8건
- velocity 피처 12건
- retrain_trigger 9건
- 앙상블 스코어링 8건
- FastAPI /v1/authorize 11건

## 성능 지표

| 지표 | 수정 전 | 수정 후 |
|------|---------|---------|
| open ROC-AUC | 0.9999 | 0.9625 ± 0.044 |
| open PR-AUC | 0.9762 | 0.7891 ± 0.049 |
| IEEE-CIS ROC-AUC | — | 0.893 ± 0.004 |
| 총 테스트 수 | ~10건 | 76건 |

자세한 내용은 PR_SUMMARY.md 참고.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" \
  --base main

# 3. PR 상태 확인
gh pr view
