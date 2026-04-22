"""consume-pattern — AI 기반 지능형 소비 패턴 분석 서비스."""

import os
from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Sentry 초기화 ──────────────────────────────────────────────────────────────
sentry_sdk.init(
    dsn=os.getenv(
        "SENTRY_DSN",
        "https://4ad1c4529600394a7438de72bfe995a0@o4511263347834880.ingest.us.sentry.io/4511263403606016",
    ),
    integrations=[
        FastApiIntegration(),       # 요청/응답 자동 추적
        SqlalchemyIntegration(),    # DB 쿼리 성능 추적
    ],
    traces_sample_rate=1.0,         # 100% 트레이싱 (운영 시 0.1~0.2 권장)
    send_default_pii=False,         # 개인정보 미전송
    environment=os.getenv("ENV", "development"),
)
# ──────────────────────────────────────────────────────────────────────────────

from app.api import (
    routes_analysis,
    routes_auth,
    routes_education,
    routes_emotion,
    routes_fido,
    routes_health,
    routes_notifications,
    routes_profile,
    routes_seed,
    routes_security_dashboard,
    routes_stepup,
    routes_strategy,
    routes_train,
    routes_xai,
)
from app.config import settings
from app.db.redis import close_redis
from app.db.session import close_db, init_db


async def _run_alembic_upgrade() -> None:
    """서버 시작 시 Alembic 마이그레이션 자동 실행."""
    import subprocess
    import sys
    from pathlib import Path

    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    if not alembic_ini.exists():
        print("[Alembic] alembic.ini not found, skipping migration")
        return
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(alembic_ini.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("[Alembic] Migration complete")
        else:
            print(f"[Alembic] Migration warning: {result.stderr.strip()}")
    except Exception as e:
        print(f"[Alembic] Migration error (non-fatal): {e}")


async def _train_models_on_startup() -> None:
    """서버 시작 시 ML 모델 학습 (데이터 있을 때만)."""
    from app.db.session import async_session_factory
    from app.ml.trainer import train_all

    try:
        async with async_session_factory() as session:
            results = await train_all(session)
        trained = {k: v.get("status") for k, v in results.items()}
        print(f"[ML] Startup training: {trained}")
    except Exception as e:
        print(f"[ML] Startup training skipped: {e}")


async def _ensure_demo_account() -> None:
    """DB에 유저가 0명이면 데모 계정을 자동 생성 + 시딩.

    docker compose up → 바로 demo@test.com / demo1234 로 로그인 가능.
    """
    from sqlalchemy import func, select

    from app.api.routes_seed import seed_user_data
    from app.auth.jwt import hash_password
    from app.db.session import async_session_factory
    from app.ml.trainer import train_all
    from app.models.tables import User

    try:
        async with async_session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(User))
            if count and count > 0:
                print(f"[Demo] {count} users exist, skipping demo account creation")
                return

            # 데모 계정 생성
            demo_user = User(
                user_id="demo_user_001",
                email="demo@test.com",
                hashed_password=hash_password("demo1234"),
                nickname="데모 사용자",
                age=28,
                occupation="직장인",
                monthly_income=3500000,
            )
            session.add(demo_user)
            await session.commit()
            print("[Demo] Created demo account: demo@test.com / demo1234")

            # 데모 데이터 시딩
            result = await seed_user_data("demo_user_001", session, months=3, tx_per_month=40)
            print(f"[Demo] Seeded: {result.get('transactions_created', 0)} txs, "
                  f"{result.get('emotion_tags_created', 0)} emotions, "
                  f"{result.get('audit_logs_created', 0)} audit logs")

            # ML 모델 학습
            train_results = await train_all(session)
            trained = {k: v.get("status") for k, v in train_results.items()}
            print(f"[Demo] ML training: {trained}")
    except Exception as e:
        print(f"[Demo] Demo account setup failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from app.services.notification_service import notification_manager

    print(f"[{settings.APP_NAME}] Starting v{settings.APP_VERSION} on :{settings.PORT}")
    await _run_alembic_upgrade()
    try:
        await asyncio.wait_for(init_db(), timeout=20.0)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[DB] init_db skipped (will retry on first request): {e}")
    try:
        await asyncio.wait_for(_ensure_demo_account(), timeout=30.0)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[Demo] Demo account setup skipped: {e}")
    try:
        await asyncio.wait_for(_train_models_on_startup(), timeout=20.0)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[ML] Startup training skipped: {e}")
    await notification_manager.start_redis_subscriber()
    yield
    await notification_manager.stop()
    await close_db()
    await close_redis()
    print(f"[{settings.APP_NAME}] Shutting down")


app = FastAPI(
    title="consume-pattern",
    description="AI 기반 지능형 소비 패턴 분석 & 데이터 기반 소비 전략 제안",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_fido.router)
app.include_router(routes_stepup.router)
app.include_router(routes_profile.router)
app.include_router(routes_analysis.router)
app.include_router(routes_strategy.router)
app.include_router(routes_seed.router)
app.include_router(routes_education.router)
app.include_router(routes_train.router)
app.include_router(routes_notifications.router)
app.include_router(routes_xai.router)
app.include_router(routes_emotion.router)
app.include_router(routes_security_dashboard.router)
