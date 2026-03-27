"""소비 전략 제안 API — 개인화 추천, 예산, 절약."""

from fastapi import APIRouter, HTTPException

from app.ml.classifier import overspend_classifier
from app.ml.clustering import cluster_model
from app.schemas.spend import BudgetSet, SpendCategory, StrategyRecommendation
from app.services.spend_profile import profile_store

router = APIRouter(prefix="/v1/strategy", tags=["strategy"])

# 인메모리 예산 저장소 (Phase 1)
_budgets: dict[str, BudgetSet] = {}


@router.get(
    "/recommend/{user_id}",
    response_model=StrategyRecommendation,
    summary="개인화 소비 전략 추천",
    description=(
        "소비 패턴 분석 결과를 바탕으로 개인화된 절약 전략과 소비 가이드라인을 제안합니다.\n\n"
        "**분석 로직**\n"
        "- K-Means 군집 → 소비 유형 라벨 부여\n"
        "- XGBoost → 과소비 위험도(risk_score) 산출\n"
        "- 규칙 기반 → 카테고리 편중, 식비/쇼핑/엔터테인먼트 임계값 초과 시 구체적 절약 방법 제시\n\n"
        "**saving_opportunities**: 절약 가능 카테고리와 예상 절감액"
    ),
    response_description="추천 목록, 절약 기회, 군집 라벨, 위험도",
)
async def recommend_strategy(user_id: str):
    """개인화 소비 전략 추천."""
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    avg = profile.avg_amount
    top_cat = profile.top_category
    breakdown = {c.category: c for c in profile.category_breakdown}

    # 규칙 기반 추천 (Phase 3에서 ML 통합)
    recommendations = []
    savings = []

    # 1) 카테고리 편중 분석 (30% 초과 시 경고)
    for cs in profile.category_breakdown:
        if cs.pct_of_total > 0.30 and cs.category.value not in ("housing", "utilities"):
            recommendations.append(
                f"{cs.category.value} 카테고리에 전체 지출의 {cs.pct_of_total*100:.0f}%가 집중되어 있습니다. "
                f"분산 소비를 고려해보세요."
            )
            savings.append({
                "category": cs.category.value,
                "potential_saving": round(cs.total_amount * 0.1, 0),
                "reason": f"{cs.category.value} 지출이 전체의 {cs.pct_of_total*100:.0f}%로 편중",
            })

    # 2) 식비 비율 체크 (15% 초과 시)
    food = breakdown.get(SpendCategory.FOOD)
    if food and food.pct_of_total > 0.15:
        potential = food.total_amount * 0.15
        recommendations.append("식비 비율이 높습니다. 자취/도시락 등으로 15% 절약이 가능합니다.")
        savings.append({
            "category": "food",
            "potential_saving": round(potential, 0),
            "reason": f"식비가 전체 지출의 {food.pct_of_total*100:.0f}%",
        })

    # 3) 쇼핑 충동 소비 체크 (건당 평균이 전체 평균의 1.2배 초과 시)
    shopping = breakdown.get(SpendCategory.SHOPPING)
    if shopping and shopping.avg_amount > avg * 1.2:
        recommendations.append("쇼핑 건당 평균이 전체 평균보다 높습니다. 구매 전 24시간 냉각기를 두세요.")
        savings.append({
            "category": "shopping",
            "potential_saving": round(shopping.total_amount * 0.2, 0),
            "reason": f"건당 평균 {shopping.avg_amount:,.0f}원 (전체 평균의 {shopping.avg_amount/avg*100:.0f}%)",
        })

    # 4) 엔터테인먼트 비율 (5% 초과 시)
    ent = breakdown.get(SpendCategory.ENTERTAINMENT)
    if ent and ent.pct_of_total > 0.05:
        recommendations.append("여가/엔터테인먼트 지출이 있습니다. 무료 대안을 탐색해보세요.")
        savings.append({
            "category": "entertainment",
            "potential_saving": round(ent.total_amount * 0.3, 0),
            "reason": f"여가비 {ent.pct_of_total*100:.0f}% 절감 가능",
        })

    # 5) 예산 대비 초과 여부
    budget = _budgets.get(user_id)
    if budget and profile.total_amount > budget.monthly_total:
        over = profile.total_amount - budget.monthly_total
        recommendations.append(
            f"설정된 월 예산({budget.monthly_total:,.0f}원)을 {over:,.0f}원 초과했습니다."
        )

    if not recommendations:
        recommendations.append("현재 소비 패턴이 안정적입니다. 좋은 습관을 유지하세요!")

    # K-Means 군집 라벨
    cat_pcts = {cs.category.value: cs.pct_of_total for cs in profile.category_breakdown}
    cluster_result = cluster_model.predict(cat_pcts)
    label = cluster_result["cluster_label"]

    # XGBoost 과소비 위험도
    top_cat_pct = profile.category_breakdown[0].pct_of_total if profile.category_breakdown else 0
    features = overspend_classifier.build_features(
        amount=avg, avg_amount=avg, category_pct=top_cat_pct,
        hour=profile.peak_hour, is_domestic=True,
        monthly_total=profile.total_amount, monthly_avg=profile.total_amount,
        recent_tx_count=profile.total_tx_count,
    )
    risk_result = overspend_classifier.predict(features)
    risk = risk_result["probability"]

    return StrategyRecommendation(
        user_id=user_id,
        cluster_label=label,
        recommendations=recommendations,
        saving_opportunities=savings,
        risk_score=risk,
    )


@router.post(
    "/budget/{user_id}",
    summary="월 예산 설정",
    description=(
        "사용자의 카테고리별 월 예산을 설정합니다.\n\n"
        "설정된 예산은 `/recommend` 추천 및 `/savings` 절약 분석에 반영됩니다.\n\n"
        "**monthly_total**: 카테고리 항목 합산으로 자동 계산됩니다."
    ),
    response_description="설정된 월 예산 총액 확인",
)
async def set_budget(user_id: str, budget: BudgetSet) -> dict:
    """카테고리별 예산 설정."""
    budget.user_id = user_id
    _budgets[user_id] = budget
    return {"status": "budget_set", "user_id": user_id, "monthly_total": budget.monthly_total}


@router.get(
    "/budget/{user_id}",
    summary="월 예산 조회",
    description="설정된 카테고리별 월 예산을 조회합니다.",
    response_description="카테고리별 예산 목록",
)
async def get_budget(user_id: str) -> dict:
    budget = _budgets.get(user_id)
    if not budget:
        raise HTTPException(404, "예산이 설정되지 않았습니다")
    return {"user_id": user_id, "budget": budget}


@router.get(
    "/savings/{user_id}",
    summary="예산 초과 절약 분석",
    description=(
        "설정된 예산과 실제 지출을 비교하여 카테고리별 초과 금액과 절감 제안을 반환합니다.\n\n"
        "예산 미설정 시 빈 목록을 반환합니다. 먼저 `POST /budget/{user_id}`로 예산을 설정하세요."
    ),
    response_description="초과 카테고리별 절감 제안 목록",
)
async def get_savings(user_id: str) -> dict:
    """절약 가능 항목 식별."""
    profile = profile_store.get_profile(user_id)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    budget = _budgets.get(user_id)
    savings = []

    for cs in profile.category_breakdown:
        if budget:
            budget_for_cat = next(
                (b.budget_amount for b in budget.items if b.category == cs.category), None
            )
            if budget_for_cat and cs.total_amount > budget_for_cat:
                savings.append({
                    "category": cs.category.value,
                    "spent": cs.total_amount,
                    "budget": budget_for_cat,
                    "over": round(cs.total_amount - budget_for_cat, 2),
                    "suggestion": f"{cs.category.value} 예산 초과 — {cs.total_amount - budget_for_cat:,.0f}원 절감 필요",
                })

    return {"user_id": user_id, "savings": savings}
