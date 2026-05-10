"""W7-#1 — Feature drift KS 검정 테스트."""
from __future__ import annotations

import random

from fastapi.testclient import TestClient

from app.main import app
from app.services.drift_detector import DriftDetector, _ks_two_sample, drift_detector

client = TestClient(app)


def test_ks_identical_distribution_zero():
    rng = random.Random(0)
    a = [rng.gauss(0, 1) for _ in range(500)]
    b = [rng.gauss(0, 1) for _ in range(500)]
    d = _ks_two_sample(a, b)
    assert d < 0.15  # 동일 분포면 KS 작음


def test_ks_shifted_distribution_large():
    rng = random.Random(1)
    a = [rng.gauss(0, 1) for _ in range(500)]
    b = [rng.gauss(3, 1) for _ in range(500)]  # 평균 +3 시프트
    d = _ks_two_sample(a, b)
    assert d > 0.7


def test_drift_detector_no_drift():
    dd = DriftDetector()
    rng = random.Random(2)
    ref = [rng.gauss(0, 1) for _ in range(500)]
    dd.set_reference("amount", ref)
    for v in [rng.gauss(0, 1) for _ in range(500)]:
        dd.record("amount", v)
    rep = dd.report(threshold=0.2)
    assert rep["any_drift"] is False
    assert rep["per_feature"]["amount"]["ref_n"] == 500
    assert rep["per_feature"]["amount"]["live_n"] == 500
    assert rep["per_feature"]["amount"]["drifted"] is False


def test_drift_detector_detects_shift():
    dd = DriftDetector()
    rng = random.Random(3)
    ref = [rng.gauss(0, 1) for _ in range(500)]
    dd.set_reference("amount", ref)
    for v in [rng.gauss(5, 1) for _ in range(500)]:
        dd.record("amount", v)
    rep = dd.report(threshold=0.2)
    assert rep["any_drift"] is True
    feat = rep["per_feature"]["amount"]
    assert feat["drifted"] is True
    assert feat["ks"] > 0.5
    assert feat["p50_diff"] > 3.0


def test_drift_detector_handles_missing_ref():
    dd = DriftDetector()
    dd.record("foo", 1.0)
    rep = dd.report()
    assert rep["per_feature"]["foo"]["drifted"] is False
    assert rep["per_feature"]["foo"]["ref_n"] == 0


def test_drift_admin_endpoint():
    drift_detector.reset()
    rng = random.Random(4)
    drift_detector.set_reference("score", [rng.gauss(0.2, 0.1) for _ in range(300)])
    for v in [rng.gauss(0.8, 0.1) for _ in range(300)]:
        drift_detector.record("score", v)
    r = client.get("/admin/api/drift?threshold=0.3")
    assert r.status_code == 200
    data = r.json()
    assert data["any_drift"] is True
    assert data["per_feature"]["score"]["drifted"] is True
    drift_detector.reset()
