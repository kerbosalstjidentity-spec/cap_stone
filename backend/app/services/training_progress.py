"""W6-#7 — 학습 진행 상태 DB 기록.

``training_runs`` 테이블에 한 회 ``train_all()`` 의 시작·종료·결과를 저장.
부분 실패 시 어떤 모델이 success/skipped/failed 상태였는지 추적 가능.

API:
- ``begin_run(session, trigger)`` — INSERT status=running, return run_id
- ``complete_run(session, run_id, results)`` — finished_at + status + per_model_status
- ``fail_run(session, run_id, error)`` — finished_at + status=failed + error
- ``recent_runs(session, limit)`` — 최근 N개 조회
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import TrainingRun


def _classify_status(results: dict) -> str:
    """per-model 결과 → 전체 status 결정."""
    statuses = []
    for k, v in results.items():
        if k == "persisted":
            continue
        if isinstance(v, dict):
            statuses.append(v.get("status", "unknown"))
        else:
            statuses.append("unknown")
    if not statuses:
        return "success"
    if all(s == "trained" for s in statuses):
        return "success"
    if any(s == "trained" for s in statuses):
        return "partial"
    return "failed"


async def begin_run(session: AsyncSession, *, trigger: str = "manual") -> int:
    run = TrainingRun(status="running", trigger=trigger)
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    return int(run_id)


async def complete_run(
    session: AsyncSession,
    run_id: int,
    results: dict,
) -> None:
    run = await session.get(TrainingRun, run_id)
    if run is None:
        return
    run.status = _classify_status(results)
    run.finished_at = datetime.now(tz=timezone.utc)
    try:
        run.per_model_status = json.dumps(results, ensure_ascii=False, default=str)
    except Exception:
        run.per_model_status = str(results)[:1000]
    await session.commit()


async def fail_run(session: AsyncSession, run_id: int, error: str) -> None:
    run = await session.get(TrainingRun, run_id)
    if run is None:
        return
    run.status = "failed"
    run.finished_at = datetime.now(tz=timezone.utc)
    run.error = (error or "")[:1000]
    await session.commit()


async def recent_runs(session: AsyncSession, limit: int = 20) -> list[dict]:
    result = await session.execute(
        select(TrainingRun).order_by(TrainingRun.id.desc()).limit(max(1, min(limit, 200)))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "trigger": r.trigger,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "per_model_status": r.per_model_status,
            "error": r.error,
        }
        for r in rows
    ]


def classify_status_sync(results: dict) -> str:
    """단위 테스트 / 동기 컨텍스트용 헬퍼."""
    return _classify_status(results)
