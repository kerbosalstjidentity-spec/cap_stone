# 💳 PayWise — AI 기반 지능형 소비 패턴 분석 서비스

> T15팀 | 캡스톤 디자인 2026

**소비는 데이터다. AI로 더 스마트하게.**

K-Means · Isolation Forest · LSTM · XGBoost 기반 소비 패턴 분석과 하이브리드 ML 사기 탐지를 하나의 플랫폼으로 통합한 풀스택 서비스입니다.

---

## 🔗 프로젝트 링크

| 도구 | 링크 | 용도 |
|------|------|------|
| 📋 **Linear** | [이슈 보드](https://linear.app/4-1-capstone/project/paywise-e507e1918672) | 태스크 & 이슈 관리 |
| 📝 **Notion** | [프로젝트 위키](https://www.notion.so/34a4df5bdfa8816db2cbc92a76b69958) | 문서 & 요구사항 |
| 🐛 **Sentry** | [에러 모니터링](https://minseo-jung.sentry.io/projects/python-fastapi/) | 실시간 에러 추적 |

---

## 🏗️ 시스템 구성

```
┌─────────────┐    ┌─────────────────────────────┐    ┌──────────────┐
│  Frontend   │───▶│         Backend API          │───▶│  ML Engine   │
│  Next.js 14 │    │  FastAPI + PostgreSQL + Redis │    │ K-Means · IF │
│  TypeScript │    │       Alembic · JWT · FIDO    │    │ LSTM · XGBoost│
└─────────────┘    └─────────────────────────────┘    └──────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │       fraud-service        │
                    │  IF · RF · Hybrid IF+RF    │
                    │    규칙 엔진 · Step-up Auth  │
                    └───────────────────────────┘
```

## 🤖 ML 모델

| 모델 | 역할 | 학습 방식 |
|------|------|-----------|
| K-Means | 소비 유형 군집화 (절약형/균형형/소비형/투자형) | 비지도 |
| Isolation Forest | 이상 거래 실시간 탐지 | 비지도 |
| LSTM | 월별 지출 예측 | 지도 (시계열) |
| XGBoost | 과소비 분류 + feature importance | 지도 |
| Hybrid IF+RF | IF 스코어 → RF 최종 분류 | 비지도+지도 |

## ⚡ 빠른 시작

```bash
# 전체 서비스 실행 (Docker)
docker-compose up --build

# 로컬 개별 실행
cd backend && .\run_local.ps1        # http://localhost:8000/docs
cd frontend && npm run dev           # http://localhost:3000
cd fraud-service && .\run_local.ps1  # http://localhost:8010/admin

# 데모 데이터 시드
curl -X POST http://localhost:8000/v1/seed/demo/demo_user_001
```

## 🛠️ 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | FastAPI · PostgreSQL · Redis · Alembic · SQLAlchemy |
| Frontend | Next.js 14 · TypeScript · Recharts · Tailwind CSS |
| ML | scikit-learn · XGBoost · PyTorch (LSTM) · SHAP |
| Auth | JWT · FIDO2 · TOTP (2FA) · WebAuthn |
| Infra | Docker Compose · Sentry · GitHub Actions (예정) |

## 📁 폴더 구조

```
cap_stone/
├── backend/            # FastAPI 백엔드 (포트 8000)
├── frontend/           # Next.js 프론트엔드 (포트 3000)
├── fraud-service/      # 사기 탐지 추론 API (포트 8010) — 배포 대상
├── fds-research/       # FDS 연구용 실험 스크립트·결과물 (배포 X)
│                       #   · IF/RF/하이브리드 실험, IEEE-CIS·Kaggle 벤치마크
│                       #   · 산출물은 fraud-service/의 학습 모델로 반영됨
├── fds_scripts/        # 운영용 FDS 유틸 스크립트
├── docs/
│   ├── presentations/  # 중간/최종 발표자료
│   ├── reports_weekly/ # 주차별 진행 보고서
│   └── specs_requirements/  # 요구사항 명세서 (SRS)
└── docker-compose.yml
```

> **fds-research vs fraud-service**: `fds-research/`는 모델 탐색·실험 저장소(논문용),
> `fraud-service/`는 실제 배포되는 추론 API입니다. 연구 결과 중 채택된 모델만
> `fraud-service/`로 반영됩니다.

## 📅 발표 일정

- **중간 발표**: 2026년 4월 29일 (수) 오후 6시 · 공7-217
