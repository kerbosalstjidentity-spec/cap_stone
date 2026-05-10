"""W5-#2 — IF 정규화 quantile 자동 추정 (번들 anomaly_low/high) 테스트."""
from __future__ import annotations

from app.scoring.ensemble import (
    ANOMALY_RANGES,
    _normalize_anomaly,
    _resolve_anomaly_range,
)


def test_resolve_falls_back_to_static():
    low, high = _resolve_anomaly_range("paysim")
    assert (low, high) == ANOMALY_RANGES["paysim"]


def test_resolve_uses_bundle_quantiles():
    bundle = {"anomaly_low": -0.9, "anomaly_high": -0.2}
    low, high = _resolve_anomaly_range("paysim", bundle=bundle)
    assert low == -0.9
    assert high == -0.2


def test_resolve_invalid_bundle_falls_back():
    # low >= high → 정적 fallback
    bundle = {"anomaly_low": -0.2, "anomaly_high": -0.9}
    low, high = _resolve_anomaly_range("paysim", bundle=bundle)
    assert (low, high) == ANOMALY_RANGES["paysim"]


def test_normalize_with_bundle_quantiles_changes_output():
    raw = -0.5
    static = _normalize_anomaly(raw, domain="paysim")
    custom = _normalize_anomaly(
        raw, domain="paysim", bundle={"anomaly_low": -0.9, "anomaly_high": -0.2},
    )
    assert 0.0 <= static <= 1.0
    assert 0.0 <= custom <= 1.0
    # 다른 정규화 범위 → 다른 결과
    assert static != custom


def test_clip_bounds():
    bundle = {"anomaly_low": -0.9, "anomaly_high": -0.2}
    # -0.95 (low 밖) → low 로 클립 → 1.0 (가장 이상)
    assert _normalize_anomaly(-0.95, domain="paysim", bundle=bundle) == 1.0
    # -0.1 (high 밖) → high 로 클립 → 0.0
    assert _normalize_anomaly(-0.1, domain="paysim", bundle=bundle) == 0.0
