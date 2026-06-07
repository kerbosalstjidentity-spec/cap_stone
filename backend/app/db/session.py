"""비동기 DB 세션 관리 — SQLAlchemy 2.0 async."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# 배포(Render 등) 호환:
#  - postgresql:// → postgresql+asyncpg:// (Render 는 평문 스킴 제공, asyncpg 필요)
#  - SSL 은 DB_SSL env 로 제어: 로컬(미설정)=off(기존 동작), Render(DB_SSL=true)=on
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgresql://"):]
_db_ssl = os.environ.get("DB_SSL", "").lower() in ("1", "true", "require", "yes", "on")

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"ssl": _db_ssl, "timeout": None},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """FastAPI Depends용 세션 팩토리."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """테이블 자동 생성 (개발용). 프로덕션에서는 Alembic 사용."""
    from app.models.base import Base
    import app.models.tables  # noqa: F401  — 모델 등록

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Tables created / verified")


async def close_db() -> None:
    """앱 종료 시 커넥션 풀 정리."""
    await engine.dispose()
    print("[DB] Connection pool disposed")
