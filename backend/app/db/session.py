"""비동기 DB 세션 관리 — SQLAlchemy 2.0 async."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    # Python 3.14 + asyncpg 0.31 호환: SSL 협상 건너뛰기, 타임아웃 없음
    connect_args={"ssl": False, "timeout": None},
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
