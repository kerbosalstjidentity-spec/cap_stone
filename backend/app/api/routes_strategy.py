"""소비 전략 제안 API — 개인화 추천, 예산, 절약."""

from fastapi import APIRouter, HTTPException

from app.ml.classifier import overspend_classifier
from app.ml.clustering import cluster_model
from app.schemas.spend import BudgetSet, SpendCategory, StrategyRecommendation
from app.services.spend_profile import profile_store

router = APIRouter(prefix="/v1/strategy", tags=["strategy"])

# 인메모리 예산 저장소 (Phase 1)
_budgets: dict[str, BudgetSet] = {}


@router.get("/recommend/{user_id}", response_model=StrategyRecommendation)
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

    # 1) 카테고리 편중 분석
    for cs in profile.category_breakdown:
        if cs.pct_of_total > 0.4:
            recommendations.append(
                f"{cs.category.value} 카테고리에 전체 지출의 {cs.pct_of_total*100:.0f}%가 집중되어 있습니다. "
                f"분산 소비를 고려해보세요."
            )

    # 2) 식비 비율 체크
    food = breakdown.get(SpendCategory.FOOD)
    if food and food.pct_of_total > 0.35:
        potential = food.total_amount * 0.15
        recommendations.append("식비 비율이 높습니다. 자취/도시락 등으로 15% 절약이 가능합니다.")
        savings.append({
            "category": "food",
            "potential_saving": round(potential, 0),
            "reason": "식비가 전체 지출의 35% 초과",
        })

    # 3) 쇼핑 충동 소비 체크
    shopping = breakdown.get(SpendCategory.SHOPPING)
    if shopping and shopping.avg_amount > avg * 1.5:
        recommendations.append("쇼핑 건당 평균이 전체 평균보다 높습니다. 구매 전 24시간 냉각기를 두세요.")
        savings.append({
            "category": "shopping",
            "potential_saving": round(shopping.total_amount * 0.2, 0),
            "reason": "충동 소비 패턴 감지",
        })

    # 4) 엔터테인먼트 비율
    ent = breakdown.get(SpendCategory.ENTERTAINMENT)
    if ent and ent.pct_of_total > 0.2:
        recommendations.append("여가/엔터테인먼트 지출 비율이 높습니다. 무료 대안을 탐색해보세요.")
        savings.append({
            "category": "entertainment",
            "potential_saving": round(ent.total_amount * 0.3, 0),
            "reason": "여가비 20% 초과",
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


@router.post("/budget/{user_id}")
async def set_budget(user_id: str, budget: BudgetSet) -> dict:
    """카테고리별 예산 설정."""
    budget.user_id = user_id
    _budgets[user_id] = budget
    return {"status": "budget_set", "user_id": user_id, "monthly_total": budget.monthly_total}


@router.get("/budget/{user_id}")
async def get_budget(user_id: str) -> dict:
    budget = _budgets.get(user_id)
    if not budget:
        raise HTTPException(404, "예산이 설정되지 않았습니다")
    return {"user_id": user_id, "budget": budget}


@router.get("/savings/{user_id}")
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
