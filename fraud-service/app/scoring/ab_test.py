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
import logging
import os
import threading
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_B_PATH = os.getenv("MODEL_B_PATH", "")
_TRAFFIC_PCT = int(os.getenv("AB_TRAFFIC_PCT", "0"))

_lock = threading.Lock()
# W9-#7: soft_review 를 review 와 별도 키로 분리 (이전엔 review 에 합산)
_stats: dict[str, dict[str, int]] = defaultdict(
    lambda: {"count": 0, "block": 0, "review": 0, "soft_review": 0, "pass": 0}
)


def load_bundle_b() -> dict | None:
    """W9-#7: MODEL_B_PATH 가 설정돼 있으면 로드, 실패 시 ERROR 로그.

    이전엔 무음 실패 — A/B 평가가 비활성된 채 운영자가 인지하지 못함.
    """
    if not _MODEL_B_PATH:
        return None
    try:
        import joblib
    except ImportError:
        logger.error("ab_test.load_bundle_b: joblib 미설치 — A/B 비활성")
        return None
    try:
        bundle = joblib.load(_MODEL_B_PATH)
        if not isinstance(bundle, dict):
            logger.error("ab_test.load_bundle_b: %s 가 dict 가 아님 (%s)",
                         _MODEL_B_PATH, type(bundle).__name__)
            return None
        return bundle
    except FileNotFoundError:
        logger.error("ab_test.load_bundle_b: %s 파일 없음", _MODEL_B_PATH)
        return None
    except Exception as e:
        logger.error("ab_test.load_bundle_b: %s 로드 실패 — %s", _MODEL_B_PATH, e)
        return None


def _route_to_b(tx_id: str) -> bool:
    """tx_id 해시 기반 결정적 라우팅."""
    if _TRAFFIC_PCT <= 0:
        return False
    h = int(hashlib.md5(tx_id.encode()).hexdigest(), 16) % 100
    return h < _TRAFFIC_PCT


def _record(variant: str, action: str) -> None:
    """W9-#7: soft_review 를 별도 키로 카운트 (이전엔 review 와 혼합)."""
    with _lock:
        _stats[variant]["count"] += 1
        a = (action or "").upper()
        if a == "BLOCK":
            _stats[variant]["block"] += 1
        elif a == "REVIEW":
            _stats[variant]["review"] += 1
        elif a == "SOFT_REVIEW":
            _stats[variant]["soft_review"] += 1
        elif a == "PASS":
            _stats[variant]["pass"] += 1


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
