"""
Isolation Forest + 분류기 앙상블 스코어링.

도메인별:
- ``capstone open`` (V1..V30): pipe.named_steps['clf'] 의 predict_proba +
  optional ``bundle['isolation_forest']`` 의 score_samples → 정규화 후 가중합.
- ``paysim`` (W5.5-#3): ``rf_model`` + ``if_model`` 조합. RF 입력에 IF suspicion
  컬럼이 학습 시 합류했으므로, 추론 경로 (``score_paysim_bundle``)에서 동일하게
  추가한다. 별도 ``ensemble_score`` 호출 없이 RF 가 IF 신호를 흡수.

번들에 'isolation_forest' 키가 없으면 XGBoost 단독 사용.
앙상블 가중치: alpha(XGBoost) + beta(IsolationForest 정규화).
"""

from __future__ import annotations

from typing import Any

import numpy as np

# 앙상블 가중치 — 나중에 SYSTEM_CONFIG 또는 .env로 빼도 됨
ALPHA = 0.7   # XGBoost 비중
BETA = 0.3    # Isolation Forest 비중

# IF score_samples 정규화 범위 — 도메인별로 다름.
# (open V1..V30 분포: 대략 -0.5 ~ -0.05)
# (paysim 분포 검증 결과 -0.80 ~ -0.33, 정상 중앙값 -0.37, 사기 중앙값 -0.53 — W5.5-#4)
ANOMALY_RANGES: dict[str, tuple[float, float]] = {
    "open": (-0.5, -0.05),
    # paysim 풀 데이터 2.77M행(time_split, no_leakage 번들) IF score 분포:
    #   range [-0.79, -0.34], normal p10/p50/p90 = (-0.52, -0.39, -0.36),
    #   fraud  p10/p50/p90 = (-0.69, -0.54, -0.39).
    # LOW = fraud p10, HIGH = normal p90 — 분포 양 끝단 로 설정.
    "paysim": (-0.69, -0.36),
}


def _normalize_anomaly(raw_score: float, *, domain: str = "open") -> float:
    """``IsolationForest.score_samples()`` 반환값 → [0, 1] 이상 확률.

    ``domain`` 별로 분포가 달라 ``ANOMALY_RANGES`` 의 (LOW, HIGH) 를 사용.
    LOW = 매우 이상한 끝, HIGH = 정상 끝. 선형 클립.
    """
    low, high = ANOMALY_RANGES.get(domain, ANOMALY_RANGES["open"])
    clipped = max(low, min(high, raw_score))
    normalized = (clipped - high) / (low - high)
    return float(normalized)


def ensemble_score(
    xgb_proba: float,
    bundle: dict,
    X: np.ndarray,
) -> tuple[float, float | None]:
    """
    (ensemble_score, anomaly_score) 반환 — open(V1..V30) 번들용.
    Isolation Forest 없으면 anomaly_score=None, ensemble=xgb_proba 그대로.
    """
    iso = bundle.get("isolation_forest")
    if iso is None:
        return xgb_proba, None

    try:
        raw = float(iso.score_samples(X)[0])
        anomaly = _normalize_anomaly(raw, domain=bundle.get("domain", "open"))
        combined = ALPHA * xgb_proba + BETA * anomaly
        return round(min(combined, 1.0), 6), round(raw, 6)
    except Exception:
        return xgb_proba, None


def score_paysim_bundle(bundle: dict[str, Any], X_raw: np.ndarray) -> dict[str, Any]:
    """PaySim 번들 단건 스코어링.

    학습 시 ``train_paysim.py`` 의 입력은 ``raw_feature_names`` 12개 + IF suspicion
    1개 = 13컬럼이었다. 추론 시 동일하게 IF score 를 부착해 RF 에 통과시킨다.

    Args:
        bundle: ``model_bundle_paysim.joblib`` (domain == 'paysim').
        X_raw: 1×N 행렬 (N = len(raw_feature_names)).

    Returns:
        {"fraud_probability", "anomaly_score", "anomaly_normalized"}.
    """
    if_model = bundle["if_model"]
    rf_model = bundle["rf_model"]
    raw = float(if_model.score_samples(X_raw)[0])
    suspicion = -raw  # train_paysim.py 와 동일한 부호 변환
    X_full = np.concatenate(
        [X_raw, np.array([[suspicion]], dtype=X_raw.dtype)], axis=1
    )
    proba = float(rf_model.predict_proba(X_full)[0, 1])
    return {
        "fraud_probability": round(proba, 6),
        "anomaly_score": round(raw, 6),
        "anomaly_normalized": round(_normalize_anomaly(raw, domain="paysim"), 6),
    }
