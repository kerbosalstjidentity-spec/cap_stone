"""W5-#7: KMeans silhouette 자동 K 선정 + cold-start 플래그."""
from __future__ import annotations

import numpy as np
import pytest

from app.ml.clustering import SpendClusterModel


def _profiles(n: int, blocks: int = 3, seed: int = 0) -> list[dict[str, float]]:
    """blocks 개의 군집 패턴을 만들어 silhouette 가 동작하는 표본 생성."""
    rng = np.random.default_rng(seed)
    out = []
    base = [
        {"food": 0.7, "shopping": 0.1, "transport": 0.1, "entertainment": 0.1},
        {"food": 0.2, "shopping": 0.5, "transport": 0.1, "entertainment": 0.2},
        {"food": 0.2, "shopping": 0.1, "transport": 0.5, "entertainment": 0.2},
    ][:blocks]
    for i in range(n):
        b = base[i % blocks]
        noise = {k: float(v + rng.normal(0, 0.02)) for k, v in b.items()}
        out.append(noise)
    return out


def test_cold_start_when_too_few_profiles():
    m = SpendClusterModel(n_clusters=4)
    m.fit(_profiles(2))  # < n_clusters
    assert m.cold_start is True
    assert m.is_fitted is False
    pred = m.predict({"food": 0.4, "shopping": 0.3})
    assert pred.get("cold_start") is True
    assert pred["cluster_id"] == -1


def test_silhouette_picks_k_matching_blocks(monkeypatch):
    monkeypatch.setenv("KMEANS_AUTO_K", "1")
    m = SpendClusterModel(n_clusters=4, random_state=42)
    m.fit(_profiles(30, blocks=3))
    assert m.is_fitted is True
    assert m.cold_start is False
    # silhouette 자동 K 는 3 군집을 선호
    assert m.n_clusters == 3
    assert m.last_silhouette is not None and m.last_silhouette > 0.3


def test_auto_k_disabled_keeps_initial_k(monkeypatch):
    monkeypatch.setenv("KMEANS_AUTO_K", "0")
    m = SpendClusterModel(n_clusters=4, random_state=42)
    m.fit(_profiles(30, blocks=3))
    assert m.n_clusters == 4
    assert m.is_fitted is True


def test_select_k_helper_directly():
    rng = np.random.default_rng(0)
    # 명백히 3 군집 데이터
    X = np.vstack([
        rng.normal((0, 0), 0.1, size=(20, 2)),
        rng.normal((5, 5), 0.1, size=(20, 2)),
        rng.normal((10, 0), 0.1, size=(20, 2)),
    ])
    k, score = SpendClusterModel._select_k_by_silhouette(X, k_min=2, k_max=6)
    assert k == 3
    assert score > 0.7
