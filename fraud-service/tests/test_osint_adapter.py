"""W8-#2 — OSINT 어댑터 + 신뢰도 가중 합산 테스트."""
from __future__ import annotations

from app.services.osint_adapter import (
    AbuseIPDBAdapter,
    ThreatReport,
    combine_reports,
    lookup_with_adapters,
)


def test_abuseipdb_mock_lookup():
    a = AbuseIPDBAdapter(mock_db={"1.2.3.4": 0.9})
    r = a.lookup("1.2.3.4")
    assert r is not None
    assert r.score == 0.9
    assert r.source == "abuseipdb"
    assert r.weight == 0.8


def test_abuseipdb_unknown_returns_none():
    a = AbuseIPDBAdapter(mock_db={})
    assert a.lookup("9.9.9.9") is None


def test_lookup_many_filters_none():
    a = AbuseIPDBAdapter(mock_db={"1.1.1.1": 0.7})
    out = a.lookup_many(["1.1.1.1", "2.2.2.2"])
    assert len(out) == 1
    assert out[0].indicator == "1.1.1.1"


def test_combine_empty():
    out = combine_reports([])
    assert out == {"score": 0.0, "feeds": [], "n": 0}


def test_combine_single_report():
    r = ThreatReport(indicator="x", score=0.5, source="s", weight=1.0)
    out = combine_reports([r])
    assert out["score"] == 0.5
    assert out["n"] == 1


def test_combine_multiple_naive_bayes():
    # 두 피드 각 0.5 (effective 0.5) → 1 - 0.5^2 = 0.75
    rs = [
        ThreatReport(indicator="x", score=0.5, source="a", weight=1.0),
        ThreatReport(indicator="x", score=0.5, source="b", weight=1.0),
    ]
    out = combine_reports(rs)
    assert out["score"] == 0.75
    assert out["n"] == 2


def test_combine_with_low_weight_attenuates():
    # weight 0.1 이면 effective 0.5*0.1 = 0.05 → combined 0.05
    r = ThreatReport(indicator="x", score=0.5, source="lowtrust", weight=0.1)
    out = combine_reports([r])
    assert out["score"] == 0.05


def test_lookup_with_adapters_aggregates():
    a1 = AbuseIPDBAdapter(mock_db={"bad.ip": 0.9})
    out = lookup_with_adapters([a1], "bad.ip")
    # 0.9 * 0.8 (weight) = 0.72 → combined 0.72
    assert out["score"] == 0.72
    assert out["n"] == 1


def test_lookup_with_adapters_handles_exceptions():
    class _Bad(AbuseIPDBAdapter):
        def lookup(self, indicator):
            raise RuntimeError("api down")
    out = lookup_with_adapters([_Bad()], "x")
    assert out["n"] == 0
