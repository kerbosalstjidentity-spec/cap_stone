"""소비 패턴 분석 API — 군집, 이상 탐지, 예측, 비교.

ML 모델 연동: K-Means(clustering), Isolation Forest(anomaly),
              LSTM(forecasting), XGBoost(classifier)
"""

from fastapi import APIRouter, HTTPException

from app.ml.anomaly import anomaly_detector
from app.ml.classifier import overspend_classifier
from app.ml.clustering import cluster_model
from app.ml.forecasting import forecaster
from app.schemas.spend import (
    AnomalyItem,
    ComparisonResult,
    ForecastResult,
    SpendCategory,
)
from app.services.spend_profile import profile_store

router = APIRouter(prefix="/v1/analysis", tags=["analysis"])


@router.get("/pattern/{user_id}")
async def analyze_pattern(user_id: str):
    """K-Means 기반 소비 패턴 군집화 결과."""
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    # 카테고리별 비율 → K-Means 입력
    cat_pcts = {cs.category.value: cs.pct_of_total for cs in profile.category_breakdown}
    result = cluster_model.predict(cat_pcts)

    return {
        "user_id": user_id,
        "cluster_label": result["cluster_label"],
        "cluster_id": result["cluster_id"],
        "total_amount": profile.total_amount,
        "avg_amount": profile.avg_amount,
        "tx_count": profile.total_tx_count,
        "top_category": profile.top_category.value,
        "category_breakdown": profile.category_breakdown,
        "feature_vector": result["features"],
    }


@router.get("/anomaly/{user_id}")
async def detect_anomaly(user_id: str) -> dict:
    """Isolation Forest 기반 이상 지출 탐지."""
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    txs = profile_store.get_transactions(user_id)
    cat_list = list(SpendCategory)

    # 거래 → IF 입력 변환
    tx_dicts = [
        {
            "amount": tx.amount,
            "hour": tx.timestamp.hour,
            "is_domestic": tx.is_domestic,
            "category_idx": cat_list.index(tx.category) if tx.category in cat_list else 0,
        }
        for tx in txs
    ]

    # IF 예측
    if_results = anomaly_detector.predict(tx_dicts)

    anomalies: list[AnomalyItem] = []
    avg = profile.avg_amount
    for i, res in enumerate(if_results):
        if res["is_anomaly"]:
            tx = txs[i]
            ratio = tx.amount / avg if avg > 0 else 0
            anomalies.append(
                AnomalyItem(
                    transaction_id=tx.transaction_id,
                    amount=tx.amount,
                    category=tx.category,
                    anomaly_score=res["anomaly_score"],
                    timestamp=tx.timestamp,
                    reason=f"이상 패턴 감지 (IF score: {res['anomaly_score']:.3f}, 평균 대비 {ratio:.1f}배)",
                )
            )

    return {
        "user_id": user_id,
        "anomaly_count": len(anomalies),
        "total_transactions": len(txs),
        "avg_amount": avg,
        "anomalies": anomalies,
    }


@router.get("/forecast/{user_id}", response_model=ForecastResult)
async def forecast_spending(user_id: str):
    """LSTM 기반 다음 달 지출 예측."""
    trend = profile_store.get_trend(user_id)
    if not trend:
        raise HTTPException(404, f"User {user_id} not found or insufficient data")

    periods = sorted(trend.keys())

    # 월별 총 지출 시계열
    monthly_totals = []
    for p in periods:
        amounts = trend[p]
        total = sum(v for k, v in amounts.items() if k != "_total")
        monthly_totals.append(total)

    # LSTM 예측 (or 가중이동평균 fallback)
    pred = forecaster.predict(monthly_totals)

    # 카테고리별 예측 (직전 3개월 비율 기반 분배)
    recent = periods[-3:] if len(periods) >= 3 else periods
    cat_sums: dict[str, float] = {}
    recent_total = 0.0
    for p in recent:
        amounts = trend[p]
        for cat, amt in amounts.items():
            if cat == "_total":
                continue
            cat_sums[cat] = cat_sums.get(cat, 0.0) + amt
            recent_total += amt

    predicted_by_cat = {}
    if recent_total > 0:
        for cat, total in cat_sums.items():
            ratio = total / recent_total
            predicted_by_cat[cat] = round(pred["predicted"] * ratio, 2)

    return ForecastResult(
        user_id=user_id,
        forecast_period="next_month",
        predicted_total=pred["predicted"],
        predicted_by_category=predicted_by_cat,
        confidence=pred["confidence"],
    )


@router.get("/overspend/{user_id}")
async def predict_overspend(user_id: str):
    """XGBoost 기반 과소비 확률 예측."""
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    trend = profile_store.get_trend(user_id)
    periods = sorted(trend.keys()) if trend else []

    monthly_avg = 0.0
    if len(periods) >= 2:
        totals = [sum(v for k, v in trend[p].items() if k != "_total") for p in periods[:-1]]
        monthly_avg = sum(totals) / len(totals) if totals else 0

    current_total = 0.0
    if periods:
        current = trend[periods[-1]]
        current_total = sum(v for k, v in current.items() if k != "_total")

    top_cat_pct = profile.category_breakdown[0].pct_of_total if profile.category_breakdown else 0

    features = overspend_classifier.build_features(
        amount=profile.avg_amount,
        avg_amount=profile.avg_amount,
        category_pct=top_cat_pct,
        hour=profile.peak_hour,
        is_domestic=True,
        monthly_total=current_total,
        monthly_avg=monthly_avg,
        recent_tx_count=profile.total_tx_count,
    )

    result = overspend_classifier.predict(features)

    return {
        "user_id": user_id,
        "overspend_probability": result["probability"],
        "is_overspend": result["is_overspend"],
        "method": result["method"],
        "monthly_total": current_total,
        "monthly_avg": monthly_avg,
    }


@router.get("/compare/{user_id}", response_model=ComparisonResult)
async def compare_periods(user_id: str, current: str = "", previous: str = ""):
    """기간 비교 분석 (전월 대비)."""
    trend = profile_store.get_trend(user_id)
    if not trend:
        raise HTTPException(404, f"User {user_id} not found")

    periods = sorted(trend.keys())
    if len(periods) < 2:
        raise HTTPException(400, "비교를 위해 최소 2개월 데이터가 필요합니다")

    cur_period = current if current in trend else periods[-1]
    prev_period = previous if previous in trend else periods[-2]

    cur_data = trend[cur_period]
    prev_data = trend[prev_period]

    cur_total = sum(v for k, v in cur_data.items() if k != "_total")
    prev_total = sum(v for k, v in prev_data.items() if k != "_total")

    diff = cur_total - prev_total
    diff_pct = (diff / prev_total * 100) if prev_total > 0 else 0

    all_cats = set(list(cur_data.keys()) + list(prev_data.keys())) - {"_total"}
    cat_diffs = {}
    for cat in all_cats:
        cat_diffs[cat] = round(cur_data.get(cat, 0) - prev_data.get(cat, 0), 2)

    if diff_pct > 20:
        insight = f"전월 대비 {diff_pct:.1f}% 증가. 지출 관리가 필요합니다."
    elif diff_pct < -10:
        insight = f"전월 대비 {abs(diff_pct):.1f}% 감소. 절약 효과가 나타나고 있습니다."
    else:
        insight = f"전월 대비 비슷한 수준입니다 ({diff_pct:+.1f}%)."

    return ComparisonResult(
        user_id=user_id,
        current_period=cur_period,
        previous_period=prev_period,
        total_diff=round(diff, 2),
        total_diff_pct=round(diff_pct, 2),
        category_diffs=cat_diffs,
        insight=insight,
    )
