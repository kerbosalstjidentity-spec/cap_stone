"""XAI (Explainable AI) 엔진 — SHAP/Feature Attribution으로 ML 예측 설명."""

import logging
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ml.classifier import overspend_classifier
from app.ml.anomaly import anomaly_detector
from app.ml.clustering import cluster_model, FEATURE_CATEGORIES
from app.models.tables import Transaction

logger = logging.getLogger(__name__)

# 한국어 Feature 이름 매핑
FEATURE_KR = {
    "amount": "거래 금액",
    "avg_amount_ratio": "평균 대비 비율",
    "category_pct": "카테고리 비중",
    "hour": "거래 시간",
    "is_domestic": "국내 거래",
    "monthly_total_ratio": "월 누적 비율",
    "tx_frequency": "거래 빈도",
}

ANOMALY_FEATURE_KR = {
    "amount": "거래 금액",
    "hour": "거래 시간",
    "is_domestic": "국내 여부",
    "category_idx": "카테고리",
    "amount_log": "로그 금액",
}

CATEGORY_KR = {
    "food": "식비", "shopping": "쇼핑", "transport": "교통",
    "entertainment": "여가", "education": "교육", "healthcare": "의료",
    "housing": "주거", "utilities": "공과금", "finance": "금융",
    "travel": "여행", "other": "기타",
}

CATEGORY_LIST = [c.value for c in FEATURE_CATEGORIES]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1. SHAP — XGBoost 과소비 설명
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def explain_overspend(user_id: str, session: AsyncSession) -> dict:
    """과소비 분류기의 SHAP 기반 설명."""
    # 사용자 거래 조회 (최근 3개월)
    since = datetime.utcnow() - timedelta(days=90)
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.timestamp >= since)
        .order_by(Transaction.timestamp.desc())
    )
    txns = list(result.scalars().all())
    if not txns:
        return {"error": "거래 데이터가 없습니다."}

    # 집계 특성 계산
    amounts = [t.amount for t in txns]
    avg_amount = np.mean(amounts) if amounts else 1
    total = sum(amounts)
    monthly_avg = total / 3 if total > 0 else 1

    # 카테고리별 비율
    cat_totals: dict[str, float] = {}
    for t in txns:
        cat_totals[t.category] = cat_totals.get(t.category, 0) + t.amount
    top_cat = max(cat_totals, key=cat_totals.get) if cat_totals else "other"
    top_cat_pct = cat_totals.get(top_cat, 0) / total if total > 0 else 0

    # 최근 거래의 대표 feature 벡터
    recent = txns[0]
    features = overspend_classifier.build_features(
        amount=recent.amount,
        avg_amount=avg_amount,
        category_pct=top_cat_pct,
        hour=recent.timestamp.hour,
        is_domestic=recent.is_domestic,
        monthly_total=total,
        monthly_avg=monthly_avg,
        recent_tx_count=len(txns),
    )

    # 예측
    pred = overspend_classifier.predict(features)

    # SHAP 설명
    shap_result = overspend_classifier.explain(features)

    if shap_result["method"] == "shap":
        shap_values = shap_result["shap_values"]
        feature_list = []
        for fname, sval in shap_values.items():
            idx = overspend_classifier.feature_names.index(fname)
            feature_list.append({
                "feature": fname,
                "feature_kr": FEATURE_KR.get(fname, fname),
                "value": round(float(features[0][idx]), 4),
                "shap_value": round(float(sval), 4),
            })
        feature_list.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
        top = feature_list[0] if feature_list else None
    else:
        # Rule-based fallback 설명
        feature_list = [
            {"feature": fn, "feature_kr": FEATURE_KR.get(fn, fn),
             "value": round(float(features[0][i]), 4), "shap_value": 0.0}
            for i, fn in enumerate(overspend_classifier.feature_names)
        ]
        top = feature_list[0] if feature_list else None

    # 한국어 요약
    summary = _build_overspend_summary(pred, top)

    return {
        "user_id": user_id,
        "base_value": round(shap_result.get("base_value", 0.5), 4),
        "prediction": pred["probability"],
        "is_overspend": pred["is_overspend"],
        "features": feature_list,
        "top_factor": top["feature"] if top else "",
        "top_factor_kr": top["feature_kr"] if top else "",
        "summary_text": summary,
        "method": shap_result["method"],
    }


def _build_overspend_summary(pred: dict, top: dict | None) -> str:
    prob = pred["probability"]
    if prob >= 0.8:
        level = "매우 높음"
    elif prob >= 0.6:
        level = "높음"
    elif prob >= 0.4:
        level = "보통"
    else:
        level = "낮음"

    summary = f"과소비 위험도 {level} ({prob*100:.0f}%)"
    if top and abs(top.get("shap_value", 0)) > 0:
        direction = "증가" if top["shap_value"] > 0 else "감소"
        summary += f" — 주요 원인: {top['feature_kr']} ({direction} 방향 기여)"
    return summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2. 이상거래 Feature Contribution
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def explain_anomalies(user_id: str, session: AsyncSession) -> dict:
    """이상 거래에 대한 feature별 기여도 설명."""
    since = datetime.utcnow() - timedelta(days=90)
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.timestamp >= since)
        .order_by(Transaction.timestamp.desc())
    )
    txns = list(result.scalars().all())
    if not txns:
        return {"user_id": user_id, "explanations": [], "total_anomalies": 0}

    # 카테고리 인덱스 매핑
    cat_to_idx = {c: i for i, c in enumerate(CATEGORY_LIST)}

    tx_dicts = [
        {
            "amount": t.amount,
            "hour": t.timestamp.hour,
            "is_domestic": t.is_domestic,
            "category_idx": cat_to_idx.get(t.category, 10),
        }
        for t in txns
    ]

    # anomaly 예측
    predictions = anomaly_detector.predict(tx_dicts)

    # feature contribution 설명
    explanations_data = anomaly_detector.explain(tx_dicts)

    explanations = []
    for i, (tx, pred, expl) in enumerate(zip(txns, predictions, explanations_data)):
        if not pred.get("is_anomaly", False):
            continue
        contributions = []
        for feat, dev in expl.get("contributions", {}).items():
            contributions.append({
                "feature": feat,
                "feature_kr": ANOMALY_FEATURE_KR.get(feat, feat),
                "deviation": round(dev, 4),
            })
        contributions.sort(key=lambda x: abs(x["deviation"]), reverse=True)

        top_factor = contributions[0]["feature"] if contributions else ""
        top_factor_kr = contributions[0]["feature_kr"] if contributions else ""
        reason = _build_anomaly_reason(tx, contributions)

        explanations.append({
            "transaction_id": tx.transaction_id,
            "amount": tx.amount,
            "category": tx.category,
            "anomaly_score": pred["anomaly_score"],
            "is_anomaly": True,
            "contributions": contributions,
            "top_factor": top_factor,
            "top_factor_kr": top_factor_kr,
            "reason": reason,
        })

    return {
        "user_id": user_id,
        "explanations": explanations,
        "total_anomalies": len(explanations),
    }


def _build_anomaly_reason(tx, contributions: list) -> str:
    if not contributions:
        return "이상 패턴이 감지되었습니다."
    top = contributions[0]
    feat_kr = top["feature_kr"]
    dev = abs(top["deviation"])
    return f"{feat_kr}이(가) 평소 대비 {dev:.1f}σ 벗어남 (금액: {tx.amount:,.0f}원)"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3. 클러스터 귀속 설명
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def explain_cluster(user_id: str, session: AsyncSession) -> dict:
    """K-Means 군집 분류 결과에 대한 설명."""
    # 카테고리별 지출 비율
    since = datetime.utcnow() - timedelta(days=90)
    result = await session.execute(
        select(Transaction.category, func.sum(Transaction.amount).label("total"))
        .where(Transaction.user_id == user_id, Transaction.timestamp >= since)
        .group_by(Transaction.category)
    )
    rows = result.all()
    if not rows:
        return {"error": "거래 데이터가 없습니다."}

    grand_total = sum(r.total for r in rows)
    category_pcts = {r.category: r.total / grand_total if grand_total > 0 else 0 for r in rows}

    # 예측
    pred = cluster_model.predict(category_pcts)
    cluster_id = pred["cluster_id"]
    cluster_label = pred["cluster_label"]

    # 설명
    expl = cluster_model.explain(category_pcts)

    return {
        "user_id": user_id,
        "cluster_id": cluster_id,
        "cluster_label": cluster_label,
        "distances_to_centers": expl.get("distances_to_centers", []),
        "feature_deviations": expl.get("feature_deviations", []),
        "top_pull_toward": expl.get("top_pull_toward", ""),
        "top_pull_away": expl.get("top_pull_away", ""),
        "summary_text": expl.get("summary_text", f"'{cluster_label}' 유형으로 분류되었습니다."),
    }
