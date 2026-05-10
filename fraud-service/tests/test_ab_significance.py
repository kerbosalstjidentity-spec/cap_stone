"""W7-#7 — A/B 통계적 유의성 검정 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import ab_test
from app.scoring.ab_stats import (
    chi_square_3way,
    compute_significance,
    two_proportion_z_test,
)

client = TestClient(app)


def test_z_test_no_diff_not_significant():
    out = two_proportion_z_test(50, 1000, 50, 1000)
    assert out["z"] == 0.0
    assert out["p_value"] >= 0.99
    assert out["significant"] is False


def test_z_test_clear_diff_significant():
    # 5% vs 15% 차이 → 큰 z, p<0.001
    out = two_proportion_z_test(50, 1000, 150, 1000)
    assert abs(out["z"]) > 5
    assert out["p_value"] < 0.001
    assert out["significant"] is True


def test_z_test_empty_sample():
    out = two_proportion_z_test(0, 0, 5, 100)
    assert out["significant"] is False


def test_chi_square_no_diff():
    a = {"block": 10, "review": 20, "pass": 70, "count": 100}
    b = {"block": 10, "review": 20, "pass": 70, "count": 100}
    out = chi_square_3way(a, b)
    assert out["chi2"] == 0.0
    assert out["significant"] is False


def test_chi_square_strong_diff():
    a = {"block": 50, "review": 30, "pass": 20, "count": 100}
    b = {"block": 10, "review": 20, "pass": 70, "count": 100}
    out = chi_square_3way(a, b)
    assert out["chi2"] > 30
    assert out["p_value"] < 0.001
    assert out["significant"] is True


def test_compute_significance_admin():
    ab_test.reset_stats()
    # 시드 — 5% vs 15% block rate
    for _ in range(950):
        ab_test._record("a", "PASS")
    for _ in range(50):
        ab_test._record("a", "BLOCK")
    for _ in range(850):
        ab_test._record("b", "PASS")
    for _ in range(150):
        ab_test._record("b", "BLOCK")

    res = compute_significance()
    assert res["samples"] == {"a": 1000, "b": 1000}
    assert res["block_rate_z_test"]["significant"] is True
    assert res["action_chi_square"]["significant"] is True

    r = client.get("/admin/api/ab-significance")
    assert r.status_code == 200
    data = r.json()
    assert data["block_rate_z_test"]["significant"] is True
    ab_test.reset_stats()
