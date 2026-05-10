"""W6-#2: model_loader lru_cache 회귀.

W6-#3 으로 스키마 검증이 추가되어, 본 테스트는 검증 통과 가능한 최소 번들로 작성.
"""
from __future__ import annotations

import joblib

from app.scoring import model_loader


class _StubModel:
    def __init__(self, version: int = 1) -> None:
        self.version = version

    def predict_proba(self, X):  # noqa: D401
        return [[0.1, 0.9]]


def test_lru_cache_hit(tmp_path):
    bundle = {"domain": "open", "model": _StubModel(1), "version": "test"}
    p = tmp_path / "bundle.joblib"
    joblib.dump(bundle, p)

    model_loader.clear_model_cache()
    a = model_loader.load_model_bundle(p)
    b = model_loader.load_model_bundle(p)
    info = model_loader.model_cache_info()

    assert a is not None
    assert a is b  # 동일 객체 → 캐시 hit
    assert info["hits"] >= 1
    assert info["currsize"] == 1


def test_clear_cache_invalidates(tmp_path):
    p = tmp_path / "bundle.joblib"
    joblib.dump({"domain": "open", "model": _StubModel(1)}, p)

    model_loader.clear_model_cache()
    first = model_loader.load_model_bundle(p)
    assert first is not None and first["model"].version == 1

    # 번들 교체 + 캐시 무효화
    joblib.dump({"domain": "open", "model": _StubModel(2)}, p)
    model_loader.clear_model_cache()
    second = model_loader.load_model_bundle(p)
    assert second is not None and second["model"].version == 2


def test_missing_path_returns_none():
    model_loader.clear_model_cache()
    assert model_loader.load_model_bundle("/nonexistent/path.joblib") is None


def test_cache_info_keys():
    info = model_loader.model_cache_info()
    assert set(info.keys()) == {"hits", "misses", "currsize"}
