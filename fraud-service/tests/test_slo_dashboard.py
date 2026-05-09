"""W7.5-#6 — SLO 대시보드 (시나리오별 검출률·latency·FN/FP) 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.stats_collector import StatsCollector, _infer_scenario, stats_collector

client = TestClient(app)


def test_infer_scenario_from_prefix():
    assert _infer_scenario("VP-0001") == "VOICE_PHISHING"
    assert _infer_scenario("MM-0123") == "MONEY_MULE"
    assert _infer_scenario("ATO-9") == "ACCOUNT_TAKEOVER"
    assert _infer_scenario("CT-1") == "CARD_TESTING"
    assert _infer_scenario("MMC-1") == "MONEY_MULE_CHAIN"
    assert _infer_scenario("SMR-7") == "SMURFING"
    assert _infer_scenario("COS-2") == "CASH_OUT_SPLIT"
    assert _infer_scenario("UNKNOWN-1") is None
    assert _infer_scenario("") is None


def test_slo_summary_empty():
    sc = StatsCollector()
    s = sc.slo_summary()
    assert s["total_evaluated"] == 0
    assert s["per_scenario"] == {}
    assert s["latency"]["p99_ms"] == 0.0


def test_slo_summary_per_scenario_detection_rate():
    sc = StatsCollector()
    # VP 5건 중 4건 BLOCK, 1건 PASS → detection_rate=0.8, fn=1
    for i in range(4):
        sc.record(f"VP-{i:04d}", "BLOCK", ["AmountBlockRule"],
                  score=0.9, amount=10_000_000, latency_ms=12.0)
    sc.record("VP-9999", "PASS", [], score=0.3, amount=100_000, latency_ms=5.0)
    # MM 3건 모두 REVIEW → detection_rate=1.0
    for i in range(3):
        sc.record(f"MM-{i:04d}", "REVIEW", ["MoneyMuleRule"],
                  score=0.65, amount=2_000_000, latency_ms=8.0)
    s = sc.slo_summary()
    assert s["total_evaluated"] == 8
    vp = s["per_scenario"]["VOICE_PHISHING"]
    assert vp["total"] == 5
    assert vp["detected"] == 4
    assert vp["detection_rate"] == 0.8
    assert vp["fn"] == 1
    assert vp["fn_rate"] == 0.2
    mm = s["per_scenario"]["MONEY_MULE"]
    assert mm["detection_rate"] == 1.0
    assert mm["fn"] == 0


def test_slo_summary_latency_percentiles():
    sc = StatsCollector()
    for i, lat in enumerate([1.0, 2.0, 3.0, 5.0, 10.0, 50.0, 100.0, 200.0, 500.0, 1000.0]):
        sc.record(f"TX-{i}", "PASS", [], score=0.1, amount=1000, latency_ms=lat)
    s = sc.slo_summary()
    assert s["latency"]["p50_ms"] >= 5.0  # median 영역
    assert s["latency"]["p99_ms"] >= 500.0
    assert s["latency"]["avg_ms"] > 0


def test_slo_summary_fp_with_explicit_expected_pass():
    sc = StatsCollector()
    sc.record("CLEAN-1", "BLOCK", ["FalseAlarmRule"], score=0.9, amount=1000,
              latency_ms=5.0, scenario_label="CLEAN", expected_action="PASS")
    sc.record("CLEAN-2", "PASS", [], score=0.1, amount=1000,
              latency_ms=5.0, scenario_label="CLEAN", expected_action="PASS")
    s = sc.slo_summary()
    clean = s["per_scenario"]["CLEAN"]
    assert clean["fp"] == 1
    assert clean["fp_rate"] == 0.5
    assert clean["fn"] == 0


def test_slo_endpoint_returns_schema():
    stats_collector.reset()
    # 합성 평가 5건
    for i in range(5):
        stats_collector.record(f"VP-{i:04d}", "BLOCK", ["AmountBlockRule"],
                               score=0.9, amount=10_000_000, latency_ms=12.0)
    r = client.get("/admin/api/slo")
    assert r.status_code == 200
    body = r.json()
    assert body["total_evaluated"] >= 5
    assert "per_scenario" in body
    assert "latency" in body
    assert "timeseries" in body
    assert "VOICE_PHISHING" in body["per_scenario"]
    stats_collector.reset()


def test_slo_endpoint_empty_after_reset():
    stats_collector.reset()
    r = client.get("/admin/api/slo")
    assert r.status_code == 200
    body = r.json()
    assert body["total_evaluated"] == 0
