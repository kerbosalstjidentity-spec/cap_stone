"""W8-#4 — 감사 로그 보존 정책 모듈.

금융 컴플라이언스 (전자금융거래법 시행령 § 22조의2) 표준 5년 보존.
``audit_chain_entries`` 테이블 + JSONL 파일 양쪽에 동일 정책 적용.

설정 (env):
- ``AUDIT_RETENTION_DAYS`` (기본 1827 = 5년 + 윤년 여유)
- ``AUDIT_RETENTION_DRYRUN`` ("1" 이면 실제 삭제 안 하고 카운트만)
- ``AUDIT_RETENTION_BATCH`` (한 번에 삭제할 최대 행, 기본 1000)

API:
- ``cutoff_datetime()`` — 보존 컷오프 (UTC, days 일 이전)
- ``classify_age(ts)`` — "active" / "warning" (만료 30일 전) / "expired"
- ``count_expired_sync(rows)`` — 헬퍼: dict/orm 리스트 중 expired 개수
- ``purge_db(session)`` — async DB 삭제 (배치, 트랜잭션)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def retention_days() -> int:
    """W8-#4: 보존 기간 (일). 기본 5년 + 윤년 2일 = 1827."""
    return max(1, _env_int("AUDIT_RETENTION_DAYS", 1827))


def cutoff_datetime() -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=retention_days())


def classify_age(ts: datetime, *, now: datetime | None = None) -> str:
    """ts 의 보존 단계 분류.

    - ``active``: 만료까지 30일 이상
    - ``warning``: 만료까지 30일 미만 (도래)
    - ``expired``: 이미 컷오프 이전
    """
    now = now or datetime.now(tz=timezone.utc)
    age = (now - ts).total_seconds() / 86400.0
    if age > retention_days():
        return "expired"
    if age > retention_days() - 30:
        return "warning"
    return "active"


def count_expired_sync(items: list, ts_attr: str = "created_at") -> int:
    """리스트 입력 (dict 또는 ORM) 중 expired 개수. 운영 dryrun 카운터용."""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=retention_days())
    expired = 0
    for item in items:
        ts = item.get(ts_attr) if isinstance(item, dict) else getattr(item, ts_attr, None)
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            expired += 1
    return expired


async def purge_db(session) -> dict:
    """audit_chain_entries 에서 expired 행 일괄 삭제 (배치).

    ``AUDIT_RETENTION_DRYRUN=1`` 이면 SELECT COUNT 만 수행.
    """
    from sqlalchemy import delete, func, select
    from app.models.tables import AuditChainEntry  # type: ignore

    cutoff = cutoff_datetime()
    dry = _env_bool("AUDIT_RETENTION_DRYRUN")
    batch = max(1, _env_int("AUDIT_RETENTION_BATCH", 1000))

    count_result = await session.execute(
        select(func.count()).select_from(AuditChainEntry).where(
            AuditChainEntry.created_at < cutoff
        )
    )
    expired_count = int(count_result.scalar() or 0)
    if dry or expired_count == 0:
        return {
            "dry_run": dry, "cutoff": cutoff.isoformat(),
            "expired_count": expired_count, "deleted": 0,
        }

    # 배치 삭제 — 한 트랜잭션에 너무 많은 행 잠그지 않도록
    deleted_total = 0
    while True:
        sub = (
            select(AuditChainEntry.id)
            .where(AuditChainEntry.created_at < cutoff)
            .limit(batch)
        )
        ids_result = await session.execute(sub)
        ids = [r[0] for r in ids_result.all()]
        if not ids:
            break
        await session.execute(
            delete(AuditChainEntry).where(AuditChainEntry.id.in_(ids))
        )
        deleted_total += len(ids)
        await session.commit()
        if len(ids) < batch:
            break

    return {
        "dry_run": False, "cutoff": cutoff.isoformat(),
        "expired_count": expired_count, "deleted": deleted_total,
    }
