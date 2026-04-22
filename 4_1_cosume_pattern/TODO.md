# 조치사항 (TODO)

## 🔴 우선 (서버 실행 후)
- [ ] API 통합 테스트 실행 확인 (`pytest --run-api` 또는 직접 실행)
  - `tests/test_profile_api.py` — Profile CRUD, 배치 수집
  - `tests/test_analysis_api.py` — K-Means, IF, LSTM, XGBoost, 비교 분석
  - `tests/test_strategy_api.py` — 추천, 예산, 절약
- [ ] Backend 로컬 실행 확인 (`run_local.ps1`)
- [ ] Frontend 로컬 실행 확인 (`npm run dev`)
- [ ] 데모 데이터 시드 → 대시보드 확인 (POST /v1/seed/demo/{user_id})

## 🟡 중기
- [ ] PostgreSQL 연동 (현재 InMemory → SQLAlchemy ORM 전환)
- [ ] Redis 캐시 연동 (프로필 TTL 설정)
- [ ] LSTM 모델 학습 파이프라인 (충분한 시계열 데이터 확보 후)
- [ ] XGBoost 모델 학습 파이프라인 (과소비 레이블링 기준 확정 후)
- [ ] K-Means fit() — 다수 사용자 데이터 수집 후 군집 학습
- [ ] fraud-service 연동 실제 호출 테스트 (두 서비스 동시 실행)

## 🟢 후기
- [ ] JWT 인증 (사용자 로그인)
- [ ] 알림 기능 (예산 80% 도달 시)
- [ ] Recharts 시계열 라인 차트 (일별 추이)
- [ ] Docker Compose (backend + frontend + postgres + redis)
- [ ] CI/CD 파이프라인
- [ ] 모바일 반응형 개선
