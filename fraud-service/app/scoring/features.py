"""
요청 JSON → 모델 입력 행 (capstone open 번들: V1..V30 순서).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def features_dict_to_matrix(features: dict[str, Any], feature_names: list[str]) -> np.ndarray:
    row = [float(features.get(name, 0.0)) for name in feature_names]
    return np.array([row], dtype=np.float64)
