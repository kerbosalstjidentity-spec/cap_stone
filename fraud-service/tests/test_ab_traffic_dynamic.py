"""W7-#5 — A/B 트래픽 비율 동적 조정 API 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import ab_test

client = TestClient(app)


def setup_function(_):
    ab_test.set_traffic_pct(0)


def teardown_function(_):
    ab_test.set_traffic_pct(0)


def test_set_traffic_pct_clips():
    assert ab_test.set_traffic_pct(150) == 100
    assert ab_test.set_traffic_pct(-1) == 0
    assert ab_test.set_traffic_pct("not-int") == 0
    assert ab_test.set_traffic_pct(25) == 25
    assert ab_test.get_traffic_pct() == 25


def test_get_endpoint():
    ab_test.set_traffic_pct(10)
    r = client.get("/admin/api/ab-traffic")
    assert r.status_code == 200
    assert r.json() == {"traffic_pct": 10}


def test_patch_endpoint_ramp():
    for pct in [1, 10, 50]:
        r = client.patch("/admin/api/ab-traffic", json={"traffic_pct": pct})
        assert r.status_code == 200
        assert r.json()["traffic_pct"] == pct
        assert ab_test.get_traffic_pct() == pct


def test_patch_validates_missing_field():
    r = client.patch("/admin/api/ab-traffic", json={})
    assert r.status_code == 422
