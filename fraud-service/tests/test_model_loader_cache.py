"""W6-#2: model_loader lru_cache 회귀."""
from __future__ import annotations

import joblib

from app.scoring import model_loader


def test_lru_cache_hit(tmp_path):
    bundle = {"version": "test", "value": 1}
    p = tmp_path / "bundle.joblib"
    joblib.dump(bundle, p)

    model_loader.clear_model_cache()
    a = model_loader.load_model_bundle(p)
    b = model_loader.load_model_bundle(p)
    info = model_loader.model_cache_info()

    assert a == bundle
    assert a is b  # 동일 객체 → 캐시 hit
    assert info["hits"] >= 1
    assert info["currsize"] == 1


def test_clear_cache_invalidates(tmp_path):
    p = tmp_path / "bundle.joblib"
    joblib.dump({"v": 1}, p)

    model_loader.clear_model_cache()
    first = model_loader.load_model_bundle(p)
    assert first == {"v": 1}

    # 번들 교체 + 캐시 무효화
    joblib.dump({"v": 2}, p)
    model_loader.clear_model_cache()
    second = model_loader.load_model_bundle(p)
    assert second == {"v": 2}


def test_missing_path_returns_none():
    model_loader.clear_model_cache()
    assert model_loader.load_model_bundle("/nonexistent/path.joblib") is None


def test_cache_info_keys():
    info = model_loader.model_cache_info()
    assert set(info.keys()) == {"hits", "misses", "currsize"}
