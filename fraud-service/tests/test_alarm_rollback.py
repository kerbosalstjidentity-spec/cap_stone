"""W7-#4 — 분포 변화 알람 + 자동 롤백 테스트."""
from __future__ import annotations

import random

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import ensemble
from app.services.alarm_manager import alarm_manager
from app.services.drift_detector import drift_detector

client = TestClient(app)


def _seed_drift():
    drift_detector.reset()
    rng = random.Random(0)
    drift_detector.set_reference("amount", [rng.gauss(100, 10) for _ in range(300)])
    for v in [rng.gauss(500, 10) for _ in range(300)]:
        drift_detector.record("amount", v)


def setup_function(_):
    alarm_manager.reset()
    drift_detector.reset()
    ensemble.set_weights(alpha=0.7, beta=0.3)


def teardown_function(_):
    alarm_manager.reset()
    drift_detector.reset()
    ensemble.set_weights(alpha=0.7, beta=0.3)


def test_no_drift_no_rollback():
    rep = alarm_manager.check_and_act()
    assert rep["triggered"] is False
    assert ensemble.get_weights() == {"alpha": 0.7, "beta": 0.3}


def test_drift_triggers_rollback():
    _seed_drift()
    rep = alarm_manager.check_and_act()
    assert rep["triggered"] is True
    assert "drift" in rep["reasons"]
    assert ensemble.get_weights() == {"alpha": 0.0, "beta": 0.0}


def test_force_rollback_and_restore():
    rep = alarm_manager.check_and_act(force=True)
    assert rep["triggered"] is True
    assert "forced" in rep["reasons"]
    assert ensemble.get_weights() == {"alpha": 0.0, "beta": 0.0}
    state = alarm_manager.state()
    assert state["rolled_back"] is True
    assert state["saved_weights"]["alpha"] == 0.7

    out = alarm_manager.restore_default_weights()
    assert out["restored"] is True
    assert ensemble.get_weights() == {"alpha": 0.7, "beta": 0.3}
    assert alarm_manager.state()["rolled_back"] is False


def test_repeat_check_does_not_double_rollback():
    alarm_manager.check_and_act(force=True)
    state1 = alarm_manager.state()
    rep2 = alarm_manager.check_and_act(force=True)
    assert rep2["triggered"] is False
    assert rep2["already_rolled_back"] is True
    state2 = alarm_manager.state()
    assert state1["saved_weights"] == state2["saved_weights"]


def test_admin_endpoints():
    r = client.get("/admin/api/alarm")
    assert r.status_code == 200
    assert "rolled_back" in r.json()

    r = client.post("/admin/api/alarm/check", json={"force": True})
    assert r.status_code == 200
    assert r.json()["triggered"] is True
    assert ensemble.get_weights() == {"alpha": 0.0, "beta": 0.0}

    r = client.post("/admin/api/alarm/restore")
    assert r.status_code == 200
    assert ensemble.get_weights() == {"alpha": 0.7, "beta": 0.3}
