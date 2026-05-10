"""W5-#3 — 사용자별 적응형 step-up 임계값.

전역 0.6 대신 사용자의 최근 risk_score 분포를 학습해 ``mean + k*std`` 를
임계값으로 사용. 일반적으로 활동량이 적은 사용자(스코어 0.1~0.2 안정)는
조금만 튀어도 step-up, 본래 변동이 큰 사용자는 더 높은 값에서만 step-up.

설계 단순화 원칙:
- 글로벌 fallback: ``settings.STEPUP_RISK_THRESHOLD`` (0.6)
- 표본 < ``min_history`` (기본 10) → fallback 사용
- 적응 임계값 = clip(mean + k*std, 0.4, 0.9), k 기본 2.0
- 표본 < min_history 이거나 std==0 → fallback 사용
- in-memory deque (최근 ``window`` 건, 기본 50). 운영 환경에선 Redis 백엔드
  교체 가능 (profile_store / feedback_store 패턴).
"""

from __future__ import annotations

import math
import os
import threading
from collections import defaultdict, deque


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_GLOBAL_DEFAULT = _env_float("STEPUP_RISK_THRESHOLD", 0.6)
_MIN_HISTORY = max(2, _env_int("STEPUP_ADAPTIVE_MIN_HISTORY", 10))
_WINDOW = max(_MIN_HISTORY, _env_int("STEPUP_ADAPTIVE_WINDOW", 50))
_K_SIGMA = _env_float("STEPUP_ADAPTIVE_K", 2.0)
_LOWER = _env_float("STEPUP_ADAPTIVE_LOWER", 0.4)
_UPPER = _env_float("STEPUP_ADAPTIVE_UPPER", 0.9)


class AdaptiveStepupThreshold:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=_WINDOW)
        )

    def record_score(self, user_id: str, score: float) -> None:
        try:
            v = float(score)
        except (TypeError, ValueError):
            return
        if math.isnan(v):
            return
        with self._lock:
            self._history[user_id].append(v)

    def get_threshold(self, user_id: str) -> dict:
        """사용자별 임계값 + 산출 근거 반환."""
        with self._lock:
            samples = list(self._history.get(user_id, ()))

        if len(samples) < _MIN_HISTORY:
            return {
                "threshold": _GLOBAL_DEFAULT,
                "source": "global_default",
                "n": len(samples),
            }

        mean = sum(samples) / len(samples)
        var = sum((x - mean) ** 2 for x in samples) / (len(samples) - 1)
        std = math.sqrt(var)
        if std <= 1e-9:
            return {
                "threshold": _GLOBAL_DEFAULT,
                "source": "global_default_zero_std",
                "n": len(samples),
                "mean": round(mean, 4),
                "std": 0.0,
            }
        raw = mean + _K_SIGMA * std
        adapted = max(_LOWER, min(_UPPER, raw))
        return {
            "threshold": round(adapted, 4),
            "source": "adaptive",
            "n": len(samples),
            "mean": round(mean, 4),
            "std": round(std, 4),
            "raw_threshold": round(raw, 4),
            "k_sigma": _K_SIGMA,
        }

    def reset(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._history.clear()
            else:
                self._history.pop(user_id, None)


adaptive_stepup = AdaptiveStepupThreshold()


def get_adaptive_threshold(user_id: str) -> float:
    """사용자별 적응 임계값 (값만 반환)."""
    return float(adaptive_stepup.get_threshold(user_id)["threshold"])


def record_risk_score(user_id: str, score: float) -> None:
    adaptive_stepup.record_score(user_id, score)
