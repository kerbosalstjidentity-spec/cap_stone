"""W6-#3 — 번들 스키마 검증 테스트."""
from __future__ import annotations


from app.scoring.model_loader import validate_bundle


class _FakeProba:
    def predict_proba(self, X):  # noqa: D401
        return [[0.1, 0.9]]


class _FakeIF:
    def score_samples(self, X):
        return [-0.5]


def test_open_bundle_valid():
    ok, probs = validate_bundle({"domain": "open", "model": _FakeProba()})
    assert ok is True
    assert probs == []


def test_open_bundle_missing_model():
    ok, probs = validate_bundle({"domain": "open"})
    assert ok is False
    assert any("필수 키" in p for p in probs)


def test_open_bundle_model_no_predict_proba():
    ok, probs = validate_bundle({"domain": "open", "model": object()})
    assert ok is False
    assert any("predict_proba" in p for p in probs)


def test_paysim_bundle_valid():
    bundle = {
        "domain": "paysim",
        "if_model": _FakeIF(),
        "rf_model": _FakeProba(),
        "raw_feature_names": ["amount", "step"],
    }
    ok, _ = validate_bundle(bundle)
    assert ok is True


def test_paysim_bundle_empty_feature_names():
    bundle = {
        "domain": "paysim",
        "if_model": _FakeIF(),
        "rf_model": _FakeProba(),
        "raw_feature_names": [],
    }
    ok, probs = validate_bundle(bundle)
    assert ok is False
    assert any("raw_feature_names" in p for p in probs)


def test_optional_feature_mu_std_length_mismatch():
    ok, probs = validate_bundle({
        "domain": "open", "model": _FakeProba(),
        "feature_mu": [0.1, 0.2], "feature_std": [1.0],
    })
    assert ok is False
    assert any("길이 불일치" in p for p in probs)


def test_optional_anomaly_low_high_invalid():
    ok, probs = validate_bundle({
        "domain": "paysim",
        "if_model": _FakeIF(), "rf_model": _FakeProba(),
        "raw_feature_names": ["a"],
        "anomaly_low": -0.2, "anomaly_high": -0.5,  # 뒤집힘
    })
    assert ok is False
    assert any(">= anomaly_high" in p for p in probs)


def test_non_dict_bundle():
    ok, probs = validate_bundle("not-a-dict")
    assert ok is False
    assert "dict" in probs[0]
