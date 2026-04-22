"""
모델 A/B 테스트 라우터.

두 모델 번들(A/B)을 동시에 평가하고 결과를 비교.
운영 트래픽에는 영향 없음 — shadow 모드로 B 결과를 로깅만.

환경변수:
  MODEL_B_PATH   B 모델 번들 경로 (없으면 A/B 비활성)
  AB_TRAFFIC_PCT B로 보낼 트래픽 비율 0~100 (기본 0 = shadow only)
"""
from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from typing import Any

_MODEL_B_PATH = os.getenv("MODEL_B_PATH", "")
_TRAFFIC_PCT = int(os.getenv("AB_TRAFFIC_PCT", "0"))

_lock = threading.Lock()
_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "block": 0, "review": 0, "pass": 0})


def _route_to_b(tx_id: str) -> bool:
    """tx_id 해시 기반 결정적 라우팅."""
    if _TRAFFIC_PCT <= 0:
        return False
    h = int(hashlib.md5(tx_id.encode()).hexdigest(), 16) % 100
    return h < _TRAFFIC_PCT


def _record(variant: str, action: str) -> None:
    with _lock:
        _stats[variant]["count"] += 1
        key = action.lower().replace("_review", "").replace("soft_", "")
        if key in ("block", "review", "pass"):
            _stats[variant][key] += 1
        elif "review" in action.lower():
            _stats[variant]["review"] += 1


def shadow_evaluate(
    tx_id: str,
    X: Any,
    bundle_a: dict,
    bundle_b: dict | None,
) -> dict[str, Any]:
    """
    A 모델로 실제 스코어, B 모델로 shadow 스코어 산출.
    반환: {"score_a": float, "score_b": float | None, "serving": "a" | "b"}
    """
    import numpy as np

    def _predict(bundle: dict) -> float:
        model = bundle.get("model")
        if model is None:
            return 0.0
        proba = model.predict_proba(X)
        return float(np.asarray(proba).ravel()[0])

    score_a = _predict(bundle_a)
    score_b = _predict(bundle_b) if bundle_b else None

    serving = "b" if (_route_to_b(tx_id) and bundle_b is not None) else "a"
    final_score = score_b if serving == "b" else score_a

    return {
        "score_a": round(score_a, 6),
        "score_b": round(score_b, 6) if score_b is not None else None,
        "serving": serving,
        "score": final_score,
    }


def get_stats() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _stats.items()}


def reset_stats() -> None:
    with _lock:
        _stats.clear()
