"""W7-#1 — Feature drift 자동 탐지 (KS 검정 / 분위수 차이).

학습 시점(reference) 분포 vs 운영 시점(live) 분포를 비교해 드리프트를
탐지한다. scipy 미의존 — 양측 KS 통계량을 직접 계산.

사용:
    drift_detector.set_reference("amount", training_samples)
    drift_detector.record("amount", live_value)  # 매 거래 호출
    drift_detector.report(threshold=0.2)         # → 피처별 ks/p_approx/drifted
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from typing import Iterable

_DEFAULT_LIVE_WINDOW = 1000
_DEFAULT_REF_LIMIT = 5000


def _ks_two_sample(ref: list[float], live: list[float]) -> float:
    """양측 KS 통계량 D = max |F_ref(x) - F_live(x)|. 표본 크기 0 → 0."""
    if not ref or not live:
        return 0.0
    a = sorted(ref)
    b = sorted(live)
    i = j = 0
    fa = fb = 0.0
    n_a = len(a)
    n_b = len(b)
    d = 0.0
    while i < n_a and j < n_b:
        if a[i] <= b[j]:
            i += 1
            fa = i / n_a
        else:
            j += 1
            fb = j / n_b
        diff = abs(fa - fb)
        if diff > d:
            d = diff
    return d


def _ks_pvalue_approx(d: float, n_a: int, n_b: int) -> float:
    """Smirnov 근사 p-value (양측). n_a, n_b > 0 가정."""
    if n_a == 0 or n_b == 0:
        return 1.0
    en = math.sqrt(n_a * n_b / (n_a + n_b))
    lam = (en + 0.12 + 0.11 / en) * d
    # Q(λ) = 2 Σ (-1)^(k-1) exp(-2 k^2 λ^2)
    s = 0.0
    sign = 1.0
    for k in range(1, 101):
        term = sign * math.exp(-2.0 * (k ** 2) * (lam ** 2))
        s += term
        sign *= -1.0
        if abs(term) < 1e-10:
            break
    p = 2.0 * s
    return max(0.0, min(1.0, p))


class DriftDetector:
    def __init__(
        self,
        live_window: int = _DEFAULT_LIVE_WINDOW,
        ref_limit: int = _DEFAULT_REF_LIMIT,
    ) -> None:
        self._lock = threading.Lock()
        self._live_window = live_window
        self._ref_limit = ref_limit
        self._reference: dict[str, list[float]] = {}
        self._live: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._live_window)
        )

    def set_reference(self, feature: str, samples: Iterable[float]) -> None:
        clean = [float(x) for x in samples if x is not None and not math.isnan(float(x))]
        if len(clean) > self._ref_limit:
            # 균등 다운샘플
            step = len(clean) / self._ref_limit
            clean = [clean[int(i * step)] for i in range(self._ref_limit)]
        with self._lock:
            self._reference[feature] = clean

    def record(self, feature: str, value: float) -> None:
        if value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if math.isnan(v):
            return
        with self._lock:
            self._live[feature].append(v)

    def reset(self, feature: str | None = None) -> None:
        with self._lock:
            if feature is None:
                self._live.clear()
                self._reference.clear()
            else:
                self._live.pop(feature, None)
                self._reference.pop(feature, None)

    def _quantile_diff(self, ref: list[float], live: list[float]) -> dict[str, float]:
        if not ref or not live:
            return {"ref_p50": 0.0, "live_p50": 0.0, "p50_diff": 0.0,
                    "ref_p95": 0.0, "live_p95": 0.0, "p95_diff": 0.0}
        rs = sorted(ref)
        ls = sorted(live)

        def q(arr: list[float], p: float) -> float:
            k = max(0, min(len(arr) - 1, int(round(p * (len(arr) - 1)))))
            return arr[k]
        r50, l50 = q(rs, 0.50), q(ls, 0.50)
        r95, l95 = q(rs, 0.95), q(ls, 0.95)
        return {
            "ref_p50": round(r50, 4),
            "live_p50": round(l50, 4),
            "p50_diff": round(l50 - r50, 4),
            "ref_p95": round(r95, 4),
            "live_p95": round(l95, 4),
            "p95_diff": round(l95 - r95, 4),
        }

    def report(self, threshold: float = 0.2) -> dict:
        """피처별 KS·분위수 차이·드리프트 여부."""
        with self._lock:
            ref_snapshot = {k: list(v) for k, v in self._reference.items()}
            live_snapshot = {k: list(v) for k, v in self._live.items()}

        features = sorted(set(ref_snapshot.keys()) | set(live_snapshot.keys()))
        per_feature: dict[str, dict] = {}
        any_drift = False
        for feat in features:
            ref = ref_snapshot.get(feat, [])
            live = live_snapshot.get(feat, [])
            ks = _ks_two_sample(ref, live)
            p_val = _ks_pvalue_approx(ks, len(ref), len(live))
            drifted = (
                bool(ref) and bool(live)
                and (ks >= threshold or p_val < 0.01)
            )
            if drifted:
                any_drift = True
            per_feature[feat] = {
                "ref_n": len(ref),
                "live_n": len(live),
                "ks": round(ks, 4),
                "p_value": round(p_val, 6),
                "drifted": drifted,
                **self._quantile_diff(ref, live),
            }
        return {
            "threshold": threshold,
            "any_drift": any_drift,
            "per_feature": per_feature,
        }


drift_detector = DriftDetector()
