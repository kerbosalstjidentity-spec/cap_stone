"""W7-#3 — 점수 분포 일별 모니터링 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services.stats_collector import StatEntry, StatsCollector, stats_collector

client = TestClient(app)


def _push(sc: StatsCollector, score: float, action: str, ts: datetime,
          tx_id: str = "T-1") -> None:
    with sc._lock:
        sc._entries.append(StatEntry(
            tx_id=tx_id,
            final_action=action,
            triggered_rules=[],
            score=score,
            amount=10_000.0,
            ts=ts,
        ))


def test_score_distribution_empty():
    sc = StatsCollector()
    out = sc.score_distribution_daily(days=3)
    assert out["days"] == 3
    assert len(out["per_day"]) == 3
    assert all(d["count"] == 0 for d in out["per_day"])
    assert out["overall"]["count"] == 0


def test_score_distribution_percentiles_and_block_rate():
    sc = StatsCollector()
    today = datetime.now(tz=timezone.utc)
    # 오늘 5건: scores 0.1, 0.3, 0.5, 0.7, 0.95 — block 1건
    for s, a in [(0.1, "PASS"), (0.3, "PASS"), (0.5, "REVIEW"),
                 (0.7, "REVIEW"), (0.95, "BLOCK")]:
        _push(sc, s, a, today)
    out = sc.score_distribution_daily(days=2)
    today_str = today.strftime("%Y-%m-%d")
    rows = {r["date"]: r for r in out["per_day"]}
    row = rows[today_str]
    assert row["count"] == 5
    assert row["min"] == 0.1
    assert row["max"] == 0.95
    assert row["mean"] == round((0.1 + 0.3 + 0.5 + 0.7 + 0.95) / 5, 4)
    assert row["block_rate"] == 0.2
    assert row["p50"] == 0.5
    assert row["p99"] == 0.95
    assert out["overall"]["count"] == 5


def test_score_distribution_separates_days():
    sc = StatsCollector()
    today = datetime.now(tz=timezone.utc)
    yesterday = today - timedelta(days=1)
    _push(sc, 0.2, "PASS", yesterday)
    _push(sc, 0.9, "BLOCK", today)
    out = sc.score_distribution_daily(days=2)
    rows = {r["date"]: r for r in out["per_day"]}
    assert rows[yesterday.strftime("%Y-%m-%d")]["count"] == 1
    assert rows[yesterday.strftime("%Y-%m-%d")]["block_rate"] == 0.0
    assert rows[today.strftime("%Y-%m-%d")]["count"] == 1
    assert rows[today.strftime("%Y-%m-%d")]["block_rate"] == 1.0


def test_score_distribution_admin_endpoint():
    stats_collector.reset()
    today = datetime.now(tz=timezone.utc)
    _push(stats_collector, 0.85, "BLOCK", today, tx_id="T-API-1")
    _push(stats_collector, 0.10, "PASS", today, tx_id="T-API-2")
    r = client.get("/admin/api/score-distribution?days=1")
    assert r.status_code == 200
    data = r.json()
    assert data["days"] == 1
    assert data["overall"]["count"] >= 2
    today_row = data["per_day"][-1]
    assert today_row["count"] >= 2
    assert today_row["mean"] > 0.0
    stats_collector.reset()
