"""ProfileStore 단위 테스트."""
from datetime import datetime, timezone, timedelta
from app.services.profile_store import InMemoryProfileStore


def _store_with_history(n: int = 5, amount: float = 50_000, minutes_ago: float = 0) -> InMemoryProfileStore:
    store = InMemoryProfileStore()
    ts = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago)
    for i in range(n):
        store.ingest("u1", {
            "tx_id": f"tx{i}",
            "amount": amount,
            "timestamp": ts.isoformat(),
            "merchant_id": f"m{i % 3}",
            "hour": 14,
        })
    return store


def test_ingest_and_profile():
    store = _store_with_history(5, amount=100_000)
    p = store.get_profile("u1")
    assert p is not None
    assert p.tx_count == 5
    assert p.avg_amount == 100_000
    assert p.max_amount == 100_000
    assert p.merchant_diversity == 3


def test_profile_none_for_unknown_user():
    store = InMemoryProfileStore()
    assert store.get_profile("nobody") is None


def test_velocity_recent():
    store = InMemoryProfileStore()
    now = datetime.now(tz=timezone.utc)
    # 30초 전 거래 3건
    for i in range(3):
        store.ingest("u1", {"tx_id": f"t{i}", "amount": 1000,
                            "timestamp": (now - timedelta(seconds=30)).isoformat()})
    # 10분 전 거래 2건 (15m 범위 내, 1m/5m 범위 밖)
    for i in range(2):
        store.ingest("u1", {"tx_id": f"old{i}", "amount": 1000,
                            "timestamp": (now - timedelta(minutes=10)).isoformat()})

    assert store.get_velocity("u1", 1) == 3
    assert store.get_velocity("u1", 5) == 3
    assert store.get_velocity("u1", 15) == 5


def test_delete():
    store = _store_with_history(3)
    assert store.delete("u1") is True
    assert store.get_profile("u1") is None
    assert store.delete("u1") is False  # 두 번째 삭제는 False


def test_peak_hour():
    store = InMemoryProfileStore()
    now = datetime.now(tz=timezone.utc)
    for _ in range(5):
        store.ingest("u1", {"tx_id": "a", "amount": 1000,
                            "timestamp": now.isoformat(), "hour": 22})
    for _ in range(2):
        store.ingest("u1", {"tx_id": "b", "amount": 1000,
                            "timestamp": now.isoformat(), "hour": 14})
    p = store.get_profile("u1")
    assert p.peak_hour == 22
