"""W5-#1 — 앙상블 가중치 동적 조정 (set_weights + admin API)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import ensemble

client = TestClient(app)


def test_get_weights_default():
    ensemble.set_weights(alpha=0.7, beta=0.3)
    w = ensemble.get_weights()
    assert w["alpha"] == 0.7
    assert w["beta"] == 0.3


def test_set_weights_partial_update():
    ensemble.set_weights(alpha=0.6)
    w = ensemble.get_weights()
    assert w["alpha"] == 0.6
    # beta 는 변경되지 않음
    ensemble.set_weights(alpha=0.7, beta=0.3)  # 복원


def test_set_weights_safe_clip():
    ensemble.set_weights(alpha=-1.0, beta=99.0)
    w = ensemble.get_weights()
    assert w["alpha"] == 0.0
    assert w["beta"] == 1.5
    ensemble.set_weights(alpha=0.7, beta=0.3)


def test_admin_endpoint_get():
    ensemble.set_weights(alpha=0.7, beta=0.3)
    r = client.get("/admin/api/ensemble-weights")
    assert r.status_code == 200
    body = r.json()
    assert body["alpha"] == 0.7
    assert body["beta"] == 0.3


def test_admin_endpoint_patch():
    r = client.patch("/admin/api/ensemble-weights", json={"alpha": 0.55, "beta": 0.45})
    assert r.status_code == 200
    body = r.json()
    assert body["alpha"] == 0.55
    assert body["beta"] == 0.45
    ensemble.set_weights(alpha=0.7, beta=0.3)  # 복원
