"""W6-#4 — 번들 메타데이터 AUC 자동 검증 테스트."""
from __future__ import annotations

import joblib

from app.scoring import model_loader
from app.scoring.model_loader import _extract_auc, validate_metadata_auc


class _StubModel:
    def predict_proba(self, X):
        return [[0.1, 0.9]]


def test_extract_auc_top_level():
    assert _extract_auc({"metrics": {"auc": 0.92}}) == 0.92
    assert _extract_auc({"metrics": {"holdout_auc": 0.88}}) == 0.88


def test_extract_auc_nested_holdout():
    assert _extract_auc({"metrics": {"holdout": {"auc": 0.95}}}) == 0.95


def test_extract_auc_missing():
    assert _extract_auc({"metrics": {}}) is None
    assert _extract_auc({}) is None


def test_validate_metadata_threshold_zero_always_ok(monkeypatch):
    monkeypatch.delenv("MODEL_BUNDLE_MIN_AUC", raising=False)
    ok, _ = validate_metadata_auc({"metrics": {}})
    assert ok is True


def test_validate_metadata_below_threshold_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_BUNDLE_MIN_AUC", "0.85")
    ok, reason = validate_metadata_auc({"metrics": {"auc": 0.7}})
    assert ok is False
    assert "0.7000" in reason


def test_validate_metadata_above_threshold_passes(monkeypatch):
    monkeypatch.setenv("MODEL_BUNDLE_MIN_AUC", "0.85")
    ok, _ = validate_metadata_auc({"metrics": {"auc": 0.92}})
    assert ok is True


def test_validate_metadata_missing_metrics_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_BUNDLE_MIN_AUC", "0.85")
    ok, reason = validate_metadata_auc({})
    assert ok is False
    assert "추출 불가" in reason


def test_load_bundle_rejects_low_auc(tmp_path, monkeypatch):
    bundle = {
        "domain": "open", "model": _StubModel(),
        "metrics": {"auc": 0.5},
    }
    p = tmp_path / "b.joblib"
    joblib.dump(bundle, p)

    monkeypatch.setenv("MODEL_BUNDLE_MIN_AUC", "0.85")
    model_loader.clear_model_cache()
    out = model_loader.load_model_bundle(p)
    assert out is None  # AUC 미달 → None


def test_load_bundle_accepts_high_auc(tmp_path, monkeypatch):
    bundle = {
        "domain": "open", "model": _StubModel(),
        "metrics": {"auc": 0.95},
    }
    p = tmp_path / "b2.joblib"
    joblib.dump(bundle, p)

    monkeypatch.setenv("MODEL_BUNDLE_MIN_AUC", "0.85")
    model_loader.clear_model_cache()
    out = model_loader.load_model_bundle(p)
    assert out is not None
    assert out["metrics"]["auc"] == 0.95
