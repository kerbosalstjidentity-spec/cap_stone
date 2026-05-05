"""
요청 JSON → 모델 입력 행.

지원 도메인:
- ``capstone open`` (V1..V30 익명 PCA, Kaggle creditcard) — 레거시
- ``paysim`` (W5.5-#3 신규) — 잔액 모순·금액 비율·타입 one-hot 12피처
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def features_dict_to_matrix(features: dict[str, Any], feature_names: list[str]) -> np.ndarray:
    """원시 키→값 dict 를 ``feature_names`` 순서대로 1×N 행렬로 변환 (open 번들용)."""
    row = [float(features.get(name, 0.0)) for name in feature_names]
    return np.array([row], dtype=np.float64)


# ---------------------------------------------------------------------------
# PaySim 도메인 — train_paysim.build_features 와 1:1 호환되어야 함
# ---------------------------------------------------------------------------

def _f(payload: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    v = payload.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_paysim_row(payload: Mapping[str, Any]) -> dict[str, float]:
    """단건 트랜잭션 dict → PaySim 학습 피처 dict.

    학습 시 ``train_paysim.build_features`` 와 동일한 파생 규칙을 사용해야 inference
    consistency 가 보장된다. 누락 키는 0.0 으로 처리.

    입력 키 (필수: type, amount, oldbalance/newbalance):
        type, amount, oldbalanceOrg, newbalanceOrig,
        oldbalanceDest, newbalanceDest, nameDest, step
    """
    step = _f(payload, "step")
    amount = _f(payload, "amount")
    old_org = _f(payload, "oldbalanceOrg")
    new_org = _f(payload, "newbalanceOrig")
    old_dest = _f(payload, "oldbalanceDest")
    new_dest = _f(payload, "newbalanceDest")

    err_org = old_org - amount - new_org
    err_dest = old_dest + amount - new_dest
    ratio = amount / (old_org + 1.0)

    name_dest = str(payload.get("nameDest", "") or "")
    is_merchant = 1.0 if name_dest.startswith("M") else 0.0

    type_str = str(payload.get("type", "") or "").upper()
    is_transfer = 1.0 if type_str == "TRANSFER" else 0.0
    is_cashout = 1.0 if type_str == "CASH_OUT" else 0.0

    return {
        "step": step,
        "amount": amount,
        "oldbalanceOrg": old_org,
        "newbalanceOrig": new_org,
        "oldbalanceDest": old_dest,
        "newbalanceDest": new_dest,
        "errorBalanceOrig": err_org,
        "errorBalanceDest": err_dest,
        "amount_to_oldbalance_ratio": ratio,
        "is_dest_merchant": is_merchant,
        "type_TRANSFER": is_transfer,
        "type_CASH_OUT": is_cashout,
    }


def paysim_dict_to_matrix(
    payload: Mapping[str, Any], raw_feature_names: list[str]
) -> np.ndarray:
    """단건 PaySim 페이로드 → 1×N 행렬 (raw_feature_names 순서)."""
    row_map = build_paysim_row(payload)
    row = [float(row_map.get(name, 0.0)) for name in raw_feature_names]
    return np.array([row], dtype=np.float64)
