"""consume-pattern — AI 기반 지능형 소비 패턴 분석 서비스."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_analysis,
    routes_auth,
    routes_education,
    routes_fido,
    routes_health,
    routes_profile,
    routes_seed,
    routes_stepup,
    routes_strategy,
)
from app.config import settings
from app.db.redis import close_redis
from app.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[{settings.APP_NAME}] Starting v{settings.APP_VERSION} on :{settings.PORT}")
    await init_db()
    yield
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
