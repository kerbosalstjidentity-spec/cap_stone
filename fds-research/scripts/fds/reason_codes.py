"""배치 단위로 상위 기여 특성 요약 (버킷: |z| 가중 중요도)."""

from __future__ import annotations

import numpy as np


def top_feature_reasons(
    X: np.ndarray,
    feature_names: list[str],
    importances: np.ndarray,
    *,
    top_k: int = 3,
) -> list[str]:
    """
    각 행마다 importance * |z| 가 큰 순으로 top_k 특성 이름을 나열.
    z는 배치 내 컬럼별 표준화(평균 0, 표준편차 1) 기준.
    """
    mu = X.mean(axis=0)
    std = np.maximum(X.std(axis=0), 1e-9)
    z = np.abs((X - mu) / std)
    imp = np.asarray(importances, dtype=float)
    n = X.shape[0]
    out: list[str] = []
    for i in range(n):
        score = imp * (1.0 + z[i])
        idx = np.argsort(-score)[:top_k]
        out.append(";".join(feature_names[j] for j in idx))
    return out
