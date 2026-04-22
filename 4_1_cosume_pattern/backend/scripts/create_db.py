"""PostgreSQL 데이터베이스 생성 스크립트.

사용법: python scripts/create_db.py
"""

import asyncio

import asyncpg


async def main():
    # postgres 기본 DB에 연결하여 consume_pattern DB 생성
    conn = await asyncpg.connect(
        user="postgres", password="postgres",
        host="localhost", port=5432,
        database="postgres",
    )

    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1", "consume_pattern"
    )

    if exists:
        print("[DB] 'consume_pattern' 데이터베이스가 이미 존재합니다.")
    else:
        await conn.execute('CREATE DATABASE "consume_pattern"')
        print("[DB] 'consume_pattern' 데이터베이스를 생성했습니다.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
