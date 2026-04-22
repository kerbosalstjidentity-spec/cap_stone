"""
Isolation Forest + XGBoost 앙상블 스코어링.

번들에 'isolation_forest' 키가 없으면 XGBoost 단독 사용.
앙상블 가중치: alpha(XGBoost) + beta(IsolationForest 정규화).
"""

from __future__ import annotations

import numpy as np

# 앙상블 가중치 — 나중에 SYSTEM_CONFIG 또는 .env로 빼도 됨
ALPHA = 0.7   # XGBoost 비중
BETA = 0.3    # Isolation Forest 비중


def _normalize_anomaly(raw_score: float) -> float:
    """
    IsolationForest.score_samples() 반환값(음수, 낮을수록 이상)을 [0,1] 이상 확률로 변환.
    일반적 범위: -0.5(정상) ~ -0.1(이상) 정도.
    선형 클리핑으로 단순 정규화.
    """
    LOW, HIGH = -0.5, -0.05
    clipped = max(LOW, min(HIGH, raw_score))
    normalized = (clipped - HIGH) / (LOW - HIGH)   # 0(정상)~1(이상)
    return float(normalized)


def ensemble_score(
    xgb_proba: float,
    bundle: dict,
    X: np.ndarray,
) -> tuple[float, float | None]:
    """
    (ensemble_score, anomaly_score) 반환.
    Isolation Forest 없으면 anomaly_score=None, ensemble=xgb_proba 그대로.
    """
    iso = bundle.get("isolation_forest")
    if iso is None:
        return xgb_proba, None

    try:
        raw = float(iso.score_samples(X)[0])
        anomaly = _normalize_anomaly(raw)
        combined = ALPHA * xgb_proba + BETA * anomaly
        return round(min(combined, 1.0), 6), round(raw, 6)
    except Exception:
        return xgb_proba, None
