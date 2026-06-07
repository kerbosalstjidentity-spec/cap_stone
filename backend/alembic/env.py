"""Alembic env.py — async PostgreSQL 마이그레이션 설정."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 모델 메타데이터 등록
from app.models.base import Base
import app.models.tables  # noqa: F401
target_metadata = Base.metadata

# DB URL을 app config에서 가져오기 (배포 호환: 스킴 정규화 + DB_SSL env)
import os as _os
import ssl as _ssl
from app.config import settings
_alembic_url = settings.DATABASE_URL
if _alembic_url.startswith("postgresql://"):
    _alembic_url = "postgresql+asyncpg://" + _alembic_url[len("postgresql://"):]
config.set_main_option("sqlalchemy.url", _alembic_url)
# Render Postgres self-signed → SSL 사용하되 검증 끔
if _os.environ.get("DB_SSL", "").lower() in ("1", "true", "require", "yes", "on"):
    _alembic_ssl: object = _ssl.create_default_context()
    _alembic_ssl.check_hostname = False
    _alembic_ssl.verify_mode = _ssl.CERT_NONE
else:
    _alembic_ssl = False


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # SSL 은 DB_SSL env 로 제어 (로컬=off / Render=on)
        connect_args={"ssl": _alembic_ssl, "timeout": None},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
