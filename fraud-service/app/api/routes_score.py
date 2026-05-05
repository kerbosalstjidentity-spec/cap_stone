from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.scoring.ensemble import ensemble_score, score_paysim_bundle
from app.scoring.features import features_dict_to_matrix, paysim_dict_to_matrix
from app.scoring.model_loader import load_model_bundle
from app.scoring.reason_codes import single_reason, top_feature_reasons, reason_code_to_human

router = APIRouter()


class ScoreRequest(BaseModel):
    features: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "open 스키마: V1..V30. paysim 스키마(W5.5-#3): type, amount, "
            "oldbalanceOrg, newbalanceOrig, oldbalanceDest, newbalanceDest, "
            "nameDest, step. 없는 키는 0.0."
        ),
    )


class BatchScoreItem(BaseModel):
    tx_id: str
    features: dict[str, Any] = Field(default_factory=dict)


class BatchScoreRequest(BaseModel):
    transactions: list[BatchScoreItem]


def _load_clf_meta(bundle: dict) -> tuple | None:
    """번들에서 (pipe, feature_names, importances) 추출. 실패 시 None."""
    pipe = bundle.get("pipeline")
    names: list[str] = list(bundle.get("feature_names") or [])
    if pipe is None or not names:
        return None
    clf = pipe.named_steps.get("clf")
    importances = getattr(clf, "feature_importances_", None)
    return pipe, names, importances


@router.post("/score")
def score(req: ScoreRequest):
    bundle = load_model_bundle()
    if bundle is None:
        return {
            "fraud_probability": None,
            "detail": "MODEL_PATH 미설정 또는 파일 없음 — .env.example 참고",
        }
    if bundle.get("domain") == "paysim":
        return _score_paysim(bundle, req.features)
    meta = _load_clf_meta(bundle)
    if meta is None:
        return {"fraud_probability": None, "detail": "번들 형식 오류 (pipeline/feature_names)"}
    pipe, names, importances = meta

    X = features_dict_to_matrix(req.features, names)
    X_t = pipe.named_steps["imputer"].transform(X)
    proba = pipe.named_steps["clf"].predict_proba(X_t)[:, 1]

    xgb_proba = float(np.asarray(proba).ravel()[0])
    final_proba, anomaly_score = ensemble_score(xgb_proba, bundle, X_t)

    reason_code = ""
    reason_human: list[str] = []
    if importances is not None:
        reason_code = single_reason(X_t[0], names, importances)
        reason_human = reason_code_to_human(X_t[0], names, importances)

    return {
        "fraud_probability": final_proba,
        "xgb_probability": xgb_proba,
        "anomaly_score": anomaly_score,
        "reason_code": reason_code,
        "reason_human": reason_human,
        "feature_count": len(names),
    }


def _score_paysim(bundle: dict, features: dict[str, Any]) -> dict[str, Any]:
    """W5.5-#4 — PaySim 번들 단건 스코어링."""
    raw_names = list(bundle.get("raw_feature_names") or [])
    if not raw_names:
        return {"fraud_probability": None, "detail": "paysim 번들 형식 오류 (raw_feature_names)"}
    X = paysim_dict_to_matrix(features, raw_names)
    out = score_paysim_bundle(bundle, X)
    rf = bundle.get("rf_model")
    importances = getattr(rf, "feature_importances_", None)
    feature_names = list(bundle.get("feature_names") or raw_names)
    reason_code = ""
    reason_human: list[str] = []
    if importances is not None and len(importances) == len(feature_names):
        suspicion = -out["anomaly_score"]
        full_row = np.concatenate([X[0], np.array([suspicion], dtype=X.dtype)])
        reason_code = single_reason(full_row, feature_names, importances)
        reason_human = reason_code_to_human(full_row, feature_names, importances)
    return {
        "fraud_probability": out["fraud_probability"],
        "rf_probability": out["fraud_probability"],
        "anomaly_score": out["anomaly_score"],
        "anomaly_normalized": out["anomaly_normalized"],
        "reason_code": reason_code,
        "reason_human": reason_human,
        "feature_count": len(feature_names),
        "domain": "paysim",
    }


@router.post("/score/batch")
def score_batch(req: BatchScoreRequest):
    if not req.transactions:
        return {"results": []}

    bundle = load_model_bundle()
    if bundle is None:
        return {
            "results": None,
            "detail": "MODEL_PATH 미설정 또는 파일 없음 — .env.example 참고",
        }
    if bundle.get("domain") == "paysim":
        results = [
            {"tx_id": item.tx_id, **_score_paysim(bundle, item.features)}
            for item in req.transactions
        ]
        return {"results": results, "feature_count": len(bundle.get("feature_names") or []), "domain": "paysim"}
    meta = _load_clf_meta(bundle)
    if meta is None:
        return {"results": None, "detail": "번들 형식 오류 (pipeline/feature_names)"}
    pipe, names, importances = meta

    rows = [features_dict_to_matrix(item.features, names)[0] for item in req.transactions]
    X = np.stack(rows, axis=0)
    X_t = pipe.named_steps["imputer"].transform(X)
    probas = pipe.named_steps["clf"].predict_proba(X_t)[:, 1]

    if importances is not None:
        reasons = top_feature_reasons(X_t, names, importances)
    else:
        reasons = [""] * len(req.transactions)

    results = [
        {
            "tx_id": item.tx_id,
            "fraud_probability": float(probas[i]),
            "reason_code": reasons[i],
        }
        for i, item in enumerate(req.transactions)
    ]
    return {"results": results, "feature_count": len(names)}
