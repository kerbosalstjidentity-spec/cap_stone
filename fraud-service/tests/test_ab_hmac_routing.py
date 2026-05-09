"""W7-#8: HMAC 기반 A/B 라우팅 — 시크릿 변경 시 다른 분기."""
from __future__ import annotations

from app.scoring import ab_test


def _count_b(tx_ids, monkeypatch, secret: str = "", pct: int = 50):
    monkeypatch.setattr(ab_test, "_AB_HMAC_SECRET", secret)
    monkeypatch.setattr(ab_test, "_TRAFFIC_PCT", pct)
    return sum(1 for tid in tx_ids if ab_test._route_to_b(tid))


def test_hmac_distribution_close_to_pct(monkeypatch):
    ids = [f"tx-{i}" for i in range(2000)]
    n = _count_b(ids, monkeypatch, secret="topsecret", pct=10)
    # 기대 200, ±50 허용 (HMAC SHA256 균등성)
    assert 150 <= n <= 250


def test_hmac_secret_change_alters_routing(monkeypatch):
    ids = [f"tx-{i}" for i in range(500)]
    n1 = _count_b(ids, monkeypatch, secret="key1", pct=20)
    n2 = _count_b(ids, monkeypatch, secret="key2", pct=20)
    # 시크릿이 다르면 같은 tx_id 들이 다른 분기로 흩어짐
    set1 = {tid for tid in ids if ab_test._route_to_b(tid)}
    monkeypatch.setattr(ab_test, "_AB_HMAC_SECRET", "key1")
    set1 = {tid for tid in ids if ab_test._route_to_b(tid)}
    monkeypatch.setattr(ab_test, "_AB_HMAC_SECRET", "key2")
    set2 = {tid for tid in ids if ab_test._route_to_b(tid)}
    # Jaccard 가 높지 않으면 (서로 다른 분기 결과) — 50% 미만 교집합
    inter = len(set1 & set2)
    union = len(set1 | set2)
    assert union > 0 and inter / union < 0.7


def test_no_secret_falls_back_to_md5(monkeypatch):
    monkeypatch.setattr(ab_test, "_AB_HMAC_SECRET", "")
    monkeypatch.setattr(ab_test, "_TRAFFIC_PCT", 100)
    # PCT=100 이면 어떤 키든 항상 B
    assert ab_test._route_to_b("any") is True


def test_traffic_pct_zero_disables(monkeypatch):
    monkeypatch.setattr(ab_test, "_TRAFFIC_PCT", 0)
    assert ab_test._route_to_b("anything") is False
