"""교육 프로그램 API — 진단, 코스, 챌린지, 퀴즈, 시뮬레이션, 리더보드 (DB 기반)."""

import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.ml.classifier import overspend_classifier
from app.ml.clustering import cluster_model
from app.schemas.education import (
    CurriculumAssignment,
    DiagnosisReport,
    EduLevel,
    FraudQuizQuestion,
    FraudSimulationRequest,
    FraudSimulationResult,
    RiskGrade,
    SavingsSimulationRequest,
    SavingsSimulationResult,
    SpendingQuizQuestion,
)
from app.services.education_store import (
    CHALLENGES,
    COURSES,
    SPENDING_QUIZ_BANK,
)
from app.services import education_store_db as edu_db
from app.services.spend_profile_db import get_profile, get_transactions, get_trend

router = APIRouter(prefix="/v1/education", tags=["education"])


# ── 유틸 ──────────────────────────────────────────────────────

def _risk_grade(score: float) -> RiskGrade:
    if score < 0.2:
        return RiskGrade.SAFE
    if score < 0.4:
        return RiskGrade.CAUTION
    if score < 0.6:
        return RiskGrade.WARNING
    if score < 0.8:
        return RiskGrade.DANGER
    return RiskGrade.CRITICAL

def _risk_description(grade: RiskGrade) -> str:
    return {
        RiskGrade.SAFE: "소비 패턴이 안정적입니다. 현재 습관을 유지하세요!",
        RiskGrade.CAUTION: "약간의 주의가 필요합니다. 특정 카테고리 지출을 점검해보세요.",
        RiskGrade.WARNING: "과소비 경고 단계입니다. 예산을 재조정하고 지출을 줄여야 합니다.",
        RiskGrade.DANGER: "위험 수준입니다. 즉시 소비 패턴을 개선해야 합니다.",
        RiskGrade.CRITICAL: "심각한 상태입니다. 전문 재무 상담을 권장합니다.",
    }[grade]

def _assign_level(risk_score: float, cluster_label: str) -> EduLevel:
    if risk_score >= 0.6 or cluster_label in ("소비형",):
        return EduLevel.BEGINNER
    if risk_score >= 0.3 or cluster_label in ("균형형",):
        return EduLevel.INTERMEDIATE
    return EduLevel.ADVANCED


# ── Module 1: 소비 습관 진단 ──────────────────────────────────

@router.get(
    "/diagnosis/{user_id}",
    response_model=DiagnosisReport,
    summary="소비 습관 종합 진단",
)
async def get_diagnosis(user_id: str, session: AsyncSession = Depends(get_session)):
    profile = await get_profile(user_id, session)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found. 먼저 데모 데이터를 생성하세요.")

    cat_pcts = {cs.category.value: cs.pct_of_total for cs in profile.category_breakdown}
    cluster = cluster_model.predict(cat_pcts)
    spend_type = cluster["cluster_label"]

    type_descriptions = {
        "절약형": "전반적으로 알뜰한 소비 습관을 가지고 있습니다. 다만 필요한 곳에 적절한 투자를 놓치고 있지 않은지 점검해보세요.",
        "균형형": "수입과 지출의 균형이 잘 잡혀 있습니다. 저축률을 조금 더 높이면 더욱 안정적인 재무 상태를 만들 수 있습니다.",
        "소비형": "쇼핑과 외식 등 원하는 것에 대한 지출이 많은 편입니다. 충동 소비 패턴을 점검하고, 예산 관리 습관을 만들어 보세요.",
        "투자형": "저축과 투자에 적극적이지만, 단기 유동성이 부족할 수 있습니다. 비상금도 함께 확보하세요.",
    }
    spend_type_desc = type_descriptions.get(spend_type, "소비 패턴을 분석 중입니다.")

    top_cat_pct = profile.category_breakdown[0].pct_of_total if profile.category_breakdown else 0
    features = overspend_classifier.build_features(
        amount=profile.avg_amount, avg_amount=profile.avg_amount,
        category_pct=top_cat_pct, hour=profile.peak_hour, is_domestic=True,
        monthly_total=profile.total_amount, monthly_avg=profile.total_amount,
        recent_tx_count=profile.total_tx_count,
    )
    risk_result = overspend_classifier.predict(features)
    risk_score = risk_result["probability"]
    grade = _risk_grade(risk_score)

    from app.ml.anomaly import anomaly_detector
    from app.schemas.spend import SpendCategory
    txs = await get_transactions(user_id, session)
    cat_list = list(SpendCategory)
    tx_dicts = [
        {"amount": tx.amount, "hour": tx.timestamp.hour, "is_domestic": tx.is_domestic,
         "category_idx": cat_list.index(tx.category) if tx.category in cat_list else 0}
        for tx in txs
    ]
    if_results = anomaly_detector.predict(tx_dicts)
    anomaly_count = sum(1 for r in if_results if r["is_anomaly"])
    anomaly_highlights = []
    for i, r in enumerate(if_results):
        if r["is_anomaly"] and len(anomaly_highlights) < 3:
            tx = txs[i]
            anomaly_highlights.append(
                f"{tx.timestamp.strftime('%m/%d %H:%M')} {tx.merchant_id} {tx.amount:,.0f}원 — 평소와 다른 소비 패턴"
            )

    trend = await get_trend(user_id, session)
    periods = sorted(trend.keys()) if trend else []
    monthly_insight = "데이터 축적 중입니다."
    if len(periods) >= 2:
        cur_data = trend[periods[-1]]
        prev_data = trend[periods[-2]]
        cur_total = sum(v for k, v in cur_data.items() if k != "_total")
        prev_total = sum(v for k, v in prev_data.items() if k != "_total")
        diff_pct = ((cur_total - prev_total) / prev_total * 100) if prev_total > 0 else 0
        if diff_pct > 20:
            monthly_insight = f"전월 대비 {diff_pct:.1f}% 증가했습니다. 지출 관리가 시급합니다."
        elif diff_pct > 0:
            monthly_insight = f"전월 대비 {diff_pct:.1f}% 소폭 증가했습니다."
        elif diff_pct > -10:
            monthly_insight = f"전월과 비슷한 수준입니다 ({diff_pct:+.1f}%)."
        else:
            monthly_insight = f"전월 대비 {abs(diff_pct):.1f}% 절약했습니다! 좋은 추세입니다."

    improvements = []
    for cs in profile.category_breakdown:
        if cs.pct_of_total > 0.30 and cs.category.value not in ("housing", "utilities"):
            improvements.append(f"{cs.category.value} 비중이 {cs.pct_of_total*100:.0f}%로 높습니다. 목표: 25% 이하")
    if risk_score > 0.5:
        improvements.append("과소비 위험도가 높습니다. 예산 설정을 먼저 해보세요.")
    if anomaly_count > 0:
        improvements.append(f"이상 소비 {anomaly_count}건이 감지되었습니다. 해당 거래를 점검하세요.")
    if not improvements:
        improvements.append("전반적으로 양호합니다. 현재 습관을 유지하세요!")

    level = _assign_level(risk_score, spend_type)
    level_courses = [c.title for c in COURSES.values() if c.level == level]

    return DiagnosisReport(
        user_id=user_id,
        spend_type=spend_type,
        spend_type_description=spend_type_desc,
        risk_grade=grade,
        risk_score=round(risk_score, 3),
        risk_description=_risk_description(grade),
        monthly_insight=monthly_insight,
        anomaly_count=anomaly_count,
        anomaly_highlights=anomaly_highlights,
        improvement_points=improvements,
        recommended_level=level,
        recommended_courses=level_courses,
    )


# ── Module 2: 맞춤 교육 코스 ─────────────────────────────────

@router.get(
    "/curriculum/{user_id}",
    response_model=CurriculumAssignment,
    summary="맞춤 커리큘럼 배정",
)
async def get_curriculum(user_id: str, session: AsyncSession = Depends(get_session)):
    profile = await get_profile(user_id, session)
    if not profile:
        raise HTTPException(404, f"User {user_id} not found")

    cat_pcts = {cs.category.value: cs.pct_of_total for cs in profile.category_breakdown}
    cluster = cluster_model.predict(cat_pcts)
    top_cat_pct = profile.category_breakdown[0].pct_of_total if profile.category_breakdown else 0
    features = overspend_classifier.build_features(
        amount=profile.avg_amount, avg_amount=profile.avg_amount,
        category_pct=top_cat_pct, hour=profile.peak_hour, is_domestic=True,
        monthly_total=profile.total_amount, monthly_avg=profile.total_amount,
        recent_tx_count=profile.total_tx_count,
    )
    risk = overspend_classifier.predict(features)["probability"]
    level = _assign_level(risk, cluster["cluster_label"])

    courses = [c for c in COURSES.values() if c.level == level]
    all_progress = await edu_db.get_all_progress(user_id, session)
    completed = sum(1 for p in all_progress if p.completed and p.course_id in [c.course_id for c in courses])

    reason_map = {
        EduLevel.BEGINNER: "소비 관리 기초부터 시작하는 것을 추천합니다.",
        EduLevel.INTERMEDIATE: "기본기가 있으므로 분석 활용 단계로 진행합니다.",
        EduLevel.ADVANCED: "안정적인 소비 패턴입니다. 보안과 고급 전략을 학습합니다.",
    }

    return CurriculumAssignment(
        user_id=user_id,
        assigned_level=level,
        reason=reason_map[level],
        courses=courses,
        total_courses=len(courses),
        completed_courses=completed,
    )


@router.get("/courses", summary="전체 코스 목록")
async def list_courses():
    return {"courses": list(COURSES.values()), "total": len(COURSES)}


@router.get("/course/{course_id}", summary="코스 상세 조회")
async def get_course(course_id: str):
    course = COURSES.get(course_id)
    if not course:
        raise HTTPException(404, f"Course {course_id} not found")
    return course


@router.post("/course/{course_id}/progress", summary="코스 진행률 업데이트")
async def update_course_progress(
    course_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if course_id not in COURSES:
        raise HTTPException(404, f"Course {course_id} not found")
    try:
        progress = await edu_db.advance_course_step(user_id, course_id, session)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "completed" if progress.completed else "in_progress", "progress": progress}


@router.get("/course/{course_id}/progress/{user_id}", summary="코스 진행 상태 조회")
async def get_course_progress_endpoint(
    course_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    progress = await edu_db.get_course_progress(user_id, course_id, session)
    if not progress:
        return {"status": "not_started", "course_id": course_id, "user_id": user_id}
    return {"status": "completed" if progress.completed else "in_progress", "progress": progress}


# ── Module 3: 사기 예방 교육 (퀴즈) ──────────────────────────

_FRAUD_SCENARIOS = [
    {"summary": "평일 오후 2시, 국내 편의점에서 4,500원 결제", "amount": 4500, "hour": 14, "foreign": False, "cat": "food", "is_fraud": False,
     "rules": [], "explanation": "소액의 국내 일상 거래로 정상입니다."},
    {"summary": "새벽 3시, 해외 IP에서 150만원 전자제품 결제", "amount": 1500000, "hour": 3, "foreign": True, "cat": "shopping", "is_fraud": True,
     "rules": ["TIME_RISK", "FOREIGN_IP", "AMOUNT_REVIEW"], "explanation": "새벽 시간대 + 해외 IP + 고액 결제 = 3가지 위험 신호가 동시 발생했습니다."},
    {"summary": "점심시간, 회사 근처 식당에서 12,000원 결제", "amount": 12000, "hour": 12, "foreign": False, "cat": "food", "is_fraud": False,
     "rules": [], "explanation": "일반적인 점심 식사 패턴으로 정상입니다."},
    {"summary": "10분 내에 같은 가맹점에서 9,900원씩 5회 연속 결제", "amount": 9900, "hour": 15, "foreign": False, "cat": "shopping", "is_fraud": True,
     "rules": ["SPLIT_TXN", "VELOCITY_FREQ"], "explanation": "1만원 미만으로 분할하여 연속 결제하는 전형적인 분할 거래 사기 패턴입니다."},
    {"summary": "월급날 오전 9시, 적금 자동이체 50만원", "amount": 500000, "hour": 9, "foreign": False, "cat": "finance", "is_fraud": False,
     "rules": [], "explanation": "정기적인 금융 거래로 정상입니다."},
    {"summary": "처음 보는 해외 가맹점에서 새벽 1시에 300만원 결제", "amount": 3000000, "hour": 1, "foreign": True, "cat": "shopping", "is_fraud": True,
     "rules": ["TIME_RISK", "FOREIGN_IP", "AMOUNT_REVIEW", "NEW_MERCHANT"], "explanation": "심야 + 해외 + 고액 + 첫 거래 가맹점으로 매우 의심스러운 거래입니다."},
    {"summary": "주말 오후, 넷플릭스 구독 결제 17,000원", "amount": 17000, "hour": 16, "foreign": False, "cat": "entertainment", "is_fraud": False,
     "rules": [], "explanation": "정기 구독 서비스 결제로 정상입니다."},
    {"summary": "평균 소비의 8배인 400만원이 새로운 쇼핑몰에서 결제", "amount": 4000000, "hour": 22, "foreign": False, "cat": "shopping", "is_fraud": True,
     "rules": ["AMOUNT_REVIEW", "AMOUNT_SPIKE", "NEW_MERCHANT"], "explanation": "평소 평균의 8배 금액 + 신규 가맹점으로 이상 거래입니다."},
    {"summary": "출퇴근 시간 교통카드 1,250원 결제", "amount": 1250, "hour": 8, "foreign": False, "cat": "transport", "is_fraud": False,
     "rules": [], "explanation": "일상적인 대중교통 이용으로 정상입니다."},
    {"summary": "같은 카드로 서로 다른 2개 도시에서 30분 내 결제", "amount": 250000, "hour": 14, "foreign": False, "cat": "shopping", "is_fraud": True,
     "rules": ["VELOCITY_FREQ"], "explanation": "물리적으로 불가능한 이동 속도로, 카드 복제 의심 거래입니다."},
]


@router.post("/quiz/fraud", summary="사기 탐지 퀴즈")
async def fraud_quiz(user_id: str, count: int = 5) -> dict:
    selected = random.sample(_FRAUD_SCENARIOS, min(count, len(_FRAUD_SCENARIOS)))
    questions = [
        FraudQuizQuestion(
            question_id=f"FQ_{i+1:03d}",
            transaction_summary=s["summary"],
            amount=s["amount"],
            hour=s["hour"],
            is_foreign=s["foreign"],
            category=s["cat"],
            options=["정상 거래", "의심 거래"],
            correct_answer="의심 거래" if s["is_fraud"] else "정상 거래",
            explanation=s["explanation"],
            triggered_rules=s["rules"],
        )
        for i, s in enumerate(selected)
    ]
    return {"user_id": user_id, "questions": questions, "total": len(questions)}


@router.post("/quiz/fraud/submit", summary="사기 탐지 퀴즈 제출")
async def submit_fraud_quiz(
    user_id: str,
    answers: list[str],
    question_ids: list[str],
    session: AsyncSession = Depends(get_session),
) -> dict:
    correct = len([a for a in answers if a == "의심 거래" or a == "정상 거래"])
    score = (correct / len(answers) * 100) if answers else 0
    await edu_db.save_quiz_score(user_id, "fraud", score, len(answers), correct, session)
    return {"user_id": user_id, "score": score, "correct": correct, "total": len(answers)}


@router.post("/quiz/spending", summary="소비 습관 퀴즈")
async def spending_quiz(user_id: str, count: int = 5) -> dict:
    selected = random.sample(SPENDING_QUIZ_BANK, min(count, len(SPENDING_QUIZ_BANK)))
    questions = [
        SpendingQuizQuestion(
            question_id=q["id"], question=q["question"],
            options=q["options"], correct_answer=q["correct"],
            explanation=q["explanation"], category=q["category"],
        )
        for q in selected
    ]
    return {"user_id": user_id, "questions": questions, "total": len(questions)}


@router.post("/quiz/spending/submit", summary="소비 습관 퀴즈 제출")
async def submit_spending_quiz(
    user_id: str,
    answers: list[dict],
    session: AsyncSession = Depends(get_session),
) -> dict:
    quiz_map = {q["id"]: q["correct"] for q in SPENDING_QUIZ_BANK}
    correct = 0
    results = []
    for a in answers:
        is_correct = a.get("answer") == quiz_map.get(a.get("question_id"))
        if is_correct:
            correct += 1
        results.append({
            "question_id": a.get("question_id"),
            "your_answer": a.get("answer"),
            "correct_answer": quiz_map.get(a.get("question_id")),
            "is_correct": is_correct,
        })
    score = (correct / len(answers) * 100) if answers else 0
    await edu_db.save_quiz_score(user_id, "spending", score, len(answers), correct, session)
    return {"user_id": user_id, "score": score, "correct": correct, "total": len(answers), "results": results}


# ── Module 4: 챌린지 & 배지 ──────────────────────────────────

@router.get("/challenges", summary="챌린지 목록")
async def list_challenges():
    return {"challenges": list(CHALLENGES.values()), "total": len(CHALLENGES)}


@router.post("/challenge/{challenge_id}/enroll", summary="챌린지 참여")
async def enroll_challenge_endpoint(
    challenge_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        enrollment = await edu_db.enroll_challenge(user_id, challenge_id, session)
        return {"status": "enrolled", "enrollment": enrollment}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/challenge/{challenge_id}/progress/{user_id}", summary="챌린지 진행 상황")
async def get_challenge_progress(
    challenge_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    enrollments = await edu_db.get_user_challenges(user_id, session)
    for e in enrollments:
        if e.challenge_id == challenge_id:
            return {"status": e.status.value, "enrollment": e}
    return {"status": "not_enrolled", "challenge_id": challenge_id}


@router.post("/challenge/{challenge_id}/update", summary="챌린지 진행률 업데이트")
async def update_challenge(
    challenge_id: str,
    user_id: str,
    value: float,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        result = await edu_db.update_challenge_progress(user_id, challenge_id, value, session)
        return {"status": result.status.value, "enrollment": result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/badges/{user_id}", summary="획득 배지 목록")
async def get_badges(user_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    badges = await edu_db.get_badges(user_id, session)
    return {"user_id": user_id, "badges": badges, "total": len(badges)}


@router.get("/user-challenges/{user_id}", summary="사용자 챌린지 전체 조회")
async def get_user_challenges(user_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    enrollments = await edu_db.get_user_challenges(user_id, session)
    return {"user_id": user_id, "challenges": enrollments, "total": len(enrollments)}


@router.post("/user-challenges/{user_id}/sync", summary="챌린지 진행률 소비 데이터 기반 자동 동기화")
async def sync_challenge_progress(user_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    await edu_db.sync_challenge_progress(user_id, session)
    enrollments = await edu_db.get_user_challenges(user_id, session)
    return {"user_id": user_id, "challenges": enrollments, "total": len(enrollments)}


# ── Module 5: 시뮬레이션 ─────────────────────────────────────

@router.post(
    "/simulate/savings",
    response_model=SavingsSimulationResult,
    summary="절약 시뮬레이션",
)
async def simulate_savings(
    req: SavingsSimulationRequest,
    session: AsyncSession = Depends(get_session),
):
    profile = await get_profile(req.user_id, session)
    if not profile:
        raise HTTPException(404, f"User {req.user_id} not found")

    breakdown = {cs.category.value: cs.total_amount for cs in profile.category_breakdown}
    trend = await get_trend(req.user_id, session)
    month_count = len(trend) if trend else 1

    current_monthly = profile.total_amount / month_count
    category_savings = {}
    before_after = {}
    total_monthly_saving = 0.0

    for cat, total in breakdown.items():
        monthly_cat = total / month_count
        reduction = req.reduction_pct.get(cat, 0)
        saving = monthly_cat * reduction
        category_savings[cat] = round(saving, 0)
        before_after[cat] = {"before": round(monthly_cat, 0), "after": round(monthly_cat - saving, 0)}
        total_monthly_saving += saving

    projected = current_monthly - total_monthly_saving

    return SavingsSimulationResult(
        user_id=req.user_id,
        current_monthly=round(current_monthly, 0),
        projected_monthly=round(projected, 0),
        monthly_saving=round(total_monthly_saving, 0),
        total_saving_over_period=round(total_monthly_saving * req.months, 0),
        months=req.months,
        category_savings=category_savings,
        before_after=before_after,
    )


@router.post(
    "/simulate/fraud",
    response_model=FraudSimulationResult,
    summary="사기 시나리오 체험",
)
async def simulate_fraud(req: FraudSimulationRequest):
    rules_triggered = []
    max_action = "PASS"

    def escalate(action: str):
        nonlocal max_action
        order = {"PASS": 0, "SOFT_REVIEW": 1, "REVIEW": 2, "BLOCK": 3}
        if order.get(action, 0) > order.get(max_action, 0):
            max_action = action

    if req.amount >= 5_000_000:
        rules_triggered.append({"rule": "AMOUNT_BLOCK", "action": "BLOCK", "reason": f"금액 {req.amount:,.0f}원 >= 500만원"})
        escalate("BLOCK")
    elif req.amount >= 1_000_000:
        rules_triggered.append({"rule": "AMOUNT_REVIEW", "action": "REVIEW", "reason": f"금액 {req.amount:,.0f}원 >= 100만원"})
        escalate("REVIEW")

    if 2 <= req.hour <= 5 and req.amount >= 500_000:
        rules_triggered.append({"rule": "TIME_RISK", "action": "REVIEW", "reason": f"심야 {req.hour}시 + 고액 {req.amount:,.0f}원"})
        escalate("REVIEW")

    if req.is_foreign_ip and req.amount >= 300_000:
        rules_triggered.append({"rule": "FOREIGN_IP", "action": "REVIEW", "reason": f"해외 IP + {req.amount:,.0f}원"})
        escalate("REVIEW")

    if req.is_new_merchant and req.amount >= 200_000:
        rules_triggered.append({"rule": "NEW_MERCHANT", "action": "SOFT_REVIEW", "reason": f"첫 거래 가맹점 + {req.amount:,.0f}원"})
        escalate("SOFT_REVIEW")

    if not rules_triggered:
        rules_triggered.append({"rule": "NONE", "action": "PASS", "reason": "이상 징후 없음"})

    tips = []
    if req.is_foreign_ip:
        tips.append("해외에서 결제할 때는 카드사에 미리 여행 일정을 알리세요.")
    if 2 <= req.hour <= 5:
        tips.append("심야 시간대 결제는 사기 위험이 높습니다. 가급적 피하세요.")
    if req.amount >= 1_000_000:
        tips.append("고액 결제 시 결제 알림을 반드시 확인하세요.")
    if req.is_new_merchant:
        tips.append("처음 거래하는 가맹점은 리뷰와 평판을 먼저 확인하세요.")
    if not tips:
        tips.append("정상적인 거래 패턴입니다. 안전한 결제 습관을 유지하세요!")

    explanation_parts = []
    if max_action == "BLOCK":
        explanation_parts.append("이 거래는 차단(BLOCK) 판정을 받습니다.")
    elif max_action == "REVIEW":
        explanation_parts.append("이 거래는 검토 필요(REVIEW) 판정을 받아 본인 확인이 요구됩니다.")
    elif max_action == "SOFT_REVIEW":
        explanation_parts.append("이 거래는 주의 관찰(SOFT_REVIEW) 대상입니다.")
    else:
        explanation_parts.append("이 거래는 정상(PASS) 판정을 받습니다.")

    if len(rules_triggered) > 1:
        explanation_parts.append(f"총 {len(rules_triggered)}개의 규칙이 감지되었으며, 가장 강한 규칙이 적용됩니다.")

    return FraudSimulationResult(
        scenario={
            "amount": req.amount,
            "hour": req.hour,
            "is_foreign_ip": req.is_foreign_ip,
            "category": req.category,
            "is_new_merchant": req.is_new_merchant,
        },
        rules_triggered=rules_triggered,
        final_action=max_action,
        risk_explanation=" ".join(explanation_parts),
        prevention_tips=tips,
    )


# ── 리더보드 ──────────────────────────────────────────────────

@router.get("/leaderboard", summary="리더보드")
async def get_leaderboard(
    top_n: int = 20,
    session: AsyncSession = Depends(get_session),
) -> dict:
    entries = await edu_db.get_leaderboard(session, limit=top_n)
    return {"leaderboard": entries, "total": len(entries)}
