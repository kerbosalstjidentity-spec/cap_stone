"""PostgreSQL 대량 시드 데이터 생성 스크립트.

사용법: python scripts/seed_db.py [--users 20] [--months 6] [--tx-per-month 60]

생성되는 데이터:
- 사용자 20명 (다양한 페르소나: 사회초년생, 프리랜서, 대학생 등)
- 사용자당 6개월 × 60건 = 360건 거래 → 총 7,200건
- 교육 진행: 코스 진행, 챌린지 참여, 퀴즈 기록, 배지
- 예산 설정
- 집계 캐시
"""

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

import asyncpg

# ── 설정 ──────────────────────────────────────────────────────

DB_URL = "postgresql://postgres:postgres@localhost:5432/consume_pattern"

CATEGORIES = [
    "food", "shopping", "transport", "entertainment", "education",
    "healthcare", "housing", "utilities", "finance", "travel", "other",
]

MERCHANTS = {
    "food": ["스타벅스_강남", "배달의민족", "이마트_식품", "맘스터치", "CU편의점",
             "맥도날드_역삼", "떡볶이_분식", "서브웨이_선릉", "빽다방", "GS25_편의점",
             "버거킹_강남", "도미노피자", "피자헛_배달", "김밥천국", "본죽"],
    "shopping": ["쿠팡_배송", "네이버쇼핑", "올리브영_홍대", "무신사_의류", "다이소_잡화",
                 "애플스토어", "삼성스토어", "ABC마트_신발", "유니클로_온라인", "오늘의집_가구"],
    "transport": ["카카오택시", "서울교통공사", "쏘카_렌트", "주유소_SK", "고속버스",
                  "KTX_서울부산", "티머니_충전", "따릉이", "카카오바이크", "타다_택시"],
    "entertainment": ["넷플릭스", "CGV_영화", "스포티파이", "PC방", "노래방",
                      "디즈니플러스", "왓챠", "볼링장", "코인노래방", "방탈출카페"],
    "education": ["교보문고", "인프런_강의", "학원비", "유데미_온라인",
                  "클래스101", "패스트캠퍼스", "영어회화_수업", "코딩학원"],
    "healthcare": ["서울대병원", "올리브약국", "헬스장_PT", "안경점",
                   "치과_스케일링", "피부과", "약국_감기약", "영양제_구입"],
    "housing": ["월세_이체", "관리비", "부동산_중개료"],
    "utilities": ["KT_통신비", "한전_전기료", "서울시_수도", "도시가스", "인터넷_요금"],
    "finance": ["적금_이체", "보험료_납부", "대출_이자", "펀드_투자"],
    "travel": ["대한항공", "호텔_예약", "여행자보험", "에어비앤비", "렌터카"],
    "other": ["기타_가맹점", "ATM_인출", "송금", "벌금_과태료"],
}

AMOUNT_RANGES = {
    "food": (2500, 45000), "shopping": (5000, 250000), "transport": (1200, 35000),
    "entertainment": (3000, 30000), "education": (10000, 150000), "healthcare": (5000, 200000),
    "housing": (300000, 900000), "utilities": (15000, 120000), "finance": (100000, 500000),
    "travel": (30000, 600000), "other": (1000, 50000),
}

# 카테고리 가중치 프로필 (페르소나별)
PERSONAS = [
    {
        "type": "사회초년생_절약형", "occupations": ["신입사원", "인턴", "공무원준비생"],
        "ages": (23, 28), "income": (200, 280),
        "weights": {"food": 30, "shopping": 10, "transport": 15, "entertainment": 5,
                    "education": 5, "healthcare": 3, "housing": 15, "utilities": 5, "finance": 8, "travel": 2, "other": 2},
    },
    {
        "type": "사회초년생_소비형", "occupations": ["마케터", "디자이너", "영업사원"],
        "ages": (24, 30), "income": (250, 350),
        "weights": {"food": 35, "shopping": 25, "transport": 10, "entertainment": 12,
                    "education": 3, "healthcare": 2, "housing": 5, "utilities": 3, "finance": 2, "travel": 3, "other": 0},
    },
    {
        "type": "대학생", "occupations": ["대학생", "대학원생"],
        "ages": (20, 26), "income": (80, 150),
        "weights": {"food": 40, "shopping": 15, "transport": 12, "entertainment": 10,
                    "education": 10, "healthcare": 2, "housing": 3, "utilities": 2, "finance": 1, "travel": 3, "other": 2},
    },
    {
        "type": "프리랜서", "occupations": ["프리랜서개발자", "프리랜서디자이너", "유튜버"],
        "ages": (25, 35), "income": (200, 500),
        "weights": {"food": 25, "shopping": 15, "transport": 8, "entertainment": 8,
                    "education": 10, "healthcare": 5, "housing": 10, "utilities": 5, "finance": 10, "travel": 4, "other": 0},
    },
    {
        "type": "자산관리_미숙형", "occupations": ["서비스업종사자", "판매원", "배달라이더"],
        "ages": (22, 35), "income": (180, 300),
        "weights": {"food": 30, "shopping": 20, "transport": 10, "entertainment": 15,
                    "education": 2, "healthcare": 3, "housing": 8, "utilities": 5, "finance": 2, "travel": 5, "other": 0},
    },
]

NICKNAMES = [
    "김민수", "이서연", "박지훈", "최유나", "정현우",
    "강수진", "조태영", "윤하늘", "임재현", "한소라",
    "오세진", "문예린", "신동혁", "류미연", "배성준",
    "황지원", "전준호", "남수아", "권도윤", "송하영",
]

COURSE_IDS = [
    "L1_C1", "L1_C2", "L1_C3", "L1_C4",
    "L2_C1", "L2_C2", "L2_C3", "L2_C4",
    "L3_C1", "L3_C2", "L3_C3", "L3_C4",
]

CHALLENGE_IDS = ["coffee_save", "budget_keeper", "zero_spend", "fraud_quiz_master", "type_change"]

BADGE_DATA = {
    "coffee_save": ("라테팩터 마스터", "coffee", "커피 절약 챌린지 완료"),
    "budget_keeper": ("예산 수호자", "shield", "예산 지키기 챌린지 완료"),
    "zero_spend": ("절약왕", "star", "무지출 데이 챌린지 완료"),
    "fraud_quiz_master": ("보안 전문가", "lock", "사기 탐지 퀴즈 마스터 완료"),
    "type_change": ("습관 혁신가", "refresh", "소비 유형 개선 챌린지 완료"),
}


# ── 생성 함수 ─────────────────────────────────────────────────

def generate_users(count: int) -> list[dict]:
    """다양한 페르소나의 사용자 생성."""
    users = []
    for i in range(count):
        persona = random.choice(PERSONAS)
        nickname = NICKNAMES[i] if i < len(NICKNAMES) else f"사용자_{i+1:03d}"
        age = random.randint(*persona["ages"])
        income = random.randint(*persona["income"]) * 10000  # 만원 단위 → 원
        occupation = random.choice(persona["occupations"])

        # 레벨 배정 (소비형/미숙형 → beginner, 대학생/프리랜서 → intermediate, 절약형 → advanced)
        if persona["type"] in ("사회초년생_소비형", "자산관리_미숙형"):
            level = "beginner"
        elif persona["type"] in ("대학생", "프리랜서"):
            level = "intermediate"
        else:
            level = "advanced"

        users.append({
            "user_id": f"user_{i+1:03d}",
            "nickname": nickname,
            "age": age,
            "occupation": occupation,
            "monthly_income": float(income),
            "edu_level": level,
            "persona_type": persona["type"],
            "category_weights": persona["weights"],
        })
    return users


def generate_transactions(user: dict, months: int, tx_per_month: int) -> list[dict]:
    """한 사용자의 거래 내역 생성."""
    txs = []
    now = datetime.now(timezone.utc)
    weights = user["category_weights"]
    cats = list(weights.keys())
    cat_weights = list(weights.values())

    # 소득 기반 소비 스케일 조정
    income = user["monthly_income"]
    spending_ratio = random.uniform(0.5, 0.9)  # 소득의 50~90% 소비

    for month_offset in range(months, 0, -1):
        base_date = now - timedelta(days=month_offset * 30)
        count = tx_per_month + random.randint(-8, 8)
        month_budget = income * spending_ratio

        month_total = 0
        for j in range(count):
            cat = random.choices(cats, weights=cat_weights, k=1)[0]
            day_offset = random.randint(0, 29)
            hour = random.choices(
                range(24),
                weights=[1,1,1,1,1,2,3,5,6,5,4,8,12,8,6,5,5,7,10,8,5,3,2,1],
                k=1,
            )[0]
            minute = random.randint(0, 59)
            ts = base_date + timedelta(days=day_offset, hours=hour, minutes=minute)

            lo, hi = AMOUNT_RANGES.get(cat, (1000, 50000))
            # 소득 수준에 맞게 금액 스케일링
            scale = min(income / 3000000, 2.0)  # 300만 기준 최대 2배
            amount = round(random.randint(lo, hi) * scale / 100) * 100

            # 2% 이상 거래 삽입
            if random.random() < 0.02:
                amount = amount * random.randint(4, 8)

            # 월 예산 내로 조절 (대략적)
            if month_total + amount > month_budget * 1.3:
                amount = round(amount * 0.3 / 100) * 100

            month_total += amount
            merchants = MERCHANTS.get(cat, ["기타_가맹점"])
            merchant = random.choice(merchants)
            channels = ["app", "app", "app", "web", "offline"]

            txs.append({
                "transaction_id": f"tx_{user['user_id']}_{month_offset:02d}_{j:04d}",
                "user_id": user["user_id"],
                "amount": float(amount),
                "timestamp": ts,
                "merchant_id": merchant,
                "category": cat,
                "channel": random.choice(channels),
                "is_domestic": random.random() > 0.03,
                "memo": merchant,
            })

    return sorted(txs, key=lambda t: t["timestamp"])


def generate_education_data(user: dict) -> dict:
    """교육 관련 데이터 (코스 진행, 챌린지, 배지, 퀴즈)."""
    now = datetime.now(timezone.utc)
    data = {"courses": [], "challenges": [], "badges": [], "quizzes": [], "points": 0}

    # 코스 진행 (레벨에 따라 일부 완료)
    level_courses = {
        "beginner": ["L1_C1", "L1_C2", "L1_C3", "L1_C4"],
        "intermediate": ["L1_C1", "L1_C2", "L1_C3", "L1_C4", "L2_C1", "L2_C2", "L2_C3", "L2_C4"],
        "advanced": COURSE_IDS,
    }
    available = level_courses.get(user["edu_level"], COURSE_IDS[:4])
    total_steps_map = {c: 4 for c in COURSE_IDS}

    for cid in available:
        if random.random() < 0.7:  # 70% 확률로 시작
            ts = total_steps_map[cid]
            completed = random.random() < 0.5
            current = ts if completed else random.randint(1, ts)
            started = now - timedelta(days=random.randint(5, 60))
            data["courses"].append({
                "user_id": user["user_id"],
                "course_id": cid,
                "current_step": current,
                "total_steps": ts,
                "completed": completed,
                "started_at": started,
                "completed_at": started + timedelta(days=random.randint(1, 14)) if completed else None,
            })
            if completed:
                data["points"] += 100

    # 챌린지 참여 (1~3개)
    n_challenges = random.randint(1, 3)
    selected_challenges = random.sample(CHALLENGE_IDS, n_challenges)
    for ch_id in selected_challenges:
        status = random.choices(["active", "completed", "failed"], weights=[40, 45, 15], k=1)[0]
        started = now - timedelta(days=random.randint(3, 30))
        duration = {"coffee_save": 14, "budget_keeper": 30, "zero_spend": 7,
                    "fraud_quiz_master": 30, "type_change": 90}[ch_id]
        progress = 100.0 if status == "completed" else random.uniform(10, 90)
        data["challenges"].append({
            "user_id": user["user_id"],
            "challenge_id": ch_id,
            "status": status,
            "start_date": started,
            "end_date": started + timedelta(days=duration),
            "current_value": progress / 100,
            "target_value": 1.0,
            "progress_pct": progress,
        })
        if status == "completed":
            data["points"] += 200
            badge_name, badge_icon, desc = BADGE_DATA[ch_id]
            data["badges"].append({
                "user_id": user["user_id"],
                "badge_name": badge_name,
                "badge_icon": badge_icon,
                "description": desc,
                "challenge_id": ch_id,
                "earned_at": started + timedelta(days=random.randint(1, duration)),
            })

    # 퀴즈 기록 (2~5회)
    n_quizzes = random.randint(2, 5)
    for _ in range(n_quizzes):
        quiz_type = random.choice(["fraud", "spending"])
        total_q = 5
        correct = random.randint(1, 5)
        score = (correct / total_q) * 100
        data["quizzes"].append({
            "user_id": user["user_id"],
            "quiz_type": quiz_type,
            "score": score,
            "total_questions": total_q,
            "correct_count": correct,
            "taken_at": now - timedelta(days=random.randint(1, 30)),
        })
        data["points"] += int(score * 10 / 100)

    return data


def generate_budgets(user: dict, months: int) -> list[dict]:
    """예산 데이터 생성."""
    now = datetime.now(timezone.utc)
    budgets = []
    income = user["monthly_income"]

    # 50/30/20 법칙 기반 예산 배분 (약간의 랜덤)
    for month_offset in range(months, 0, -1):
        period = (now - timedelta(days=month_offset * 30)).strftime("%Y-%m")
        monthly_total = income * random.uniform(0.7, 0.95)

        # 카테고리별 배분
        budget_weights = user["category_weights"]
        total_weight = sum(budget_weights.values())
        for cat, weight in budget_weights.items():
            if weight == 0:
                continue
            ratio = weight / total_weight
            budgets.append({
                "user_id": user["user_id"],
                "period": period,
                "category": cat,
                "budget_amount": round(monthly_total * ratio / 1000) * 1000,  # 천원 단위
                "monthly_total": round(monthly_total / 1000) * 1000,
            })
    return budgets


def compute_profile_cache(user_id: str, txs: list[dict]) -> list[dict]:
    """월별 카테고리 집계 캐시 계산."""
    from collections import defaultdict
    monthly: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for tx in txs:
        period = tx["timestamp"].strftime("%Y-%m")
        monthly[period][tx["category"]].append(tx["amount"])

    cache = []
    for period, cats in monthly.items():
        for cat, amounts in cats.items():
            cache.append({
                "user_id": user_id,
                "period": period,
                "category": cat,
                "total_amount": sum(amounts),
                "tx_count": len(amounts),
                "avg_amount": sum(amounts) / len(amounts),
                "max_amount": max(amounts),
            })
    return cache


# ── DB 삽입 ───────────────────────────────────────────────────

async def seed(n_users: int, months: int, tx_per_month: int):
    conn = await asyncpg.connect(DB_URL)
    print(f"\n=== 시드 데이터 생성 시작 ===")
    print(f"  사용자: {n_users}명")
    print(f"  기간: {months}개월")
    print(f"  거래/월: ~{tx_per_month}건")
    print(f"  예상 총 거래: ~{n_users * months * tx_per_month:,}건\n")

    # 기존 데이터 초기화
    print("[1/7] 기존 데이터 정리...")
    for table in ["quiz_scores", "user_badges", "challenge_enrollments", "course_progress",
                  "budgets", "spend_profile_cache", "leaderboard_points", "transactions", "users"]:
        await conn.execute(f'DELETE FROM "{table}"')

    # 사용자 생성
    print("[2/7] 사용자 생성 중...")
    users = generate_users(n_users)
    now = datetime.now(timezone.utc)
    await conn.executemany(
        """INSERT INTO users (user_id, nickname, age, occupation, monthly_income, edu_level, is_active, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, true, $7, $7)""",
        [(u["user_id"], u["nickname"], u["age"], u["occupation"],
          u["monthly_income"], u["edu_level"], now)
         for u in users],
    )
    print(f"  -> {len(users)}명 생성 완료")
    for u in users:
        print(f"     {u['user_id']}: {u['nickname']} ({u['occupation']}, {u['age']}세, {u['persona_type']})")

    # 거래 내역 생성
    print("\n[3/7] 거래 내역 생성 중...")
    all_txs = []
    for u in users:
        txs = generate_transactions(u, months, tx_per_month)
        all_txs.extend(txs)

    # 배치 삽입 (1000건씩)
    batch_size = 1000
    for i in range(0, len(all_txs), batch_size):
        batch = all_txs[i:i+batch_size]
        await conn.executemany(
            """INSERT INTO transactions
               (transaction_id, user_id, amount, timestamp, merchant_id, category, channel, is_domestic, memo, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)""",
            [(t["transaction_id"], t["user_id"], t["amount"], t["timestamp"],
              t["merchant_id"], t["category"], t["channel"], t["is_domestic"], t["memo"], now)
             for t in batch],
        )
    print(f"  -> {len(all_txs):,}건 거래 생성 완료")

    # 집계 캐시 생성
    print("\n[4/7] 집계 캐시 계산 중...")
    all_cache = []
    for u in users:
        user_txs = [t for t in all_txs if t["user_id"] == u["user_id"]]
        cache = compute_profile_cache(u["user_id"], user_txs)
        all_cache.extend(cache)

    await conn.executemany(
        """INSERT INTO spend_profile_cache
           (user_id, period, category, total_amount, tx_count, avg_amount, max_amount, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)""",
        [(c["user_id"], c["period"], c["category"], c["total_amount"],
          c["tx_count"], c["avg_amount"], c["max_amount"], now)
         for c in all_cache],
    )
    print(f"  -> {len(all_cache):,}건 캐시 레코드 생성 완료")

    # 예산 데이터 생성
    print("\n[5/7] 예산 데이터 생성 중...")
    all_budgets = []
    for u in users:
        budgets = generate_budgets(u, months)
        all_budgets.extend(budgets)

    await conn.executemany(
        """INSERT INTO budgets
           (user_id, period, category, budget_amount, monthly_total, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $6)""",
        [(b["user_id"], b["period"], b["category"], b["budget_amount"], b["monthly_total"], now)
         for b in all_budgets],
    )
    print(f"  -> {len(all_budgets):,}건 예산 레코드 생성 완료")

    # 교육 데이터 생성
    print("\n[6/7] 교육 데이터 생성 중...")
    total_courses = total_challenges = total_badges = total_quizzes = 0

    for u in users:
        edu = generate_education_data(u)

        if edu["courses"]:
            await conn.executemany(
                """INSERT INTO course_progress
                   (user_id, course_id, current_step, total_steps, completed, started_at, completed_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)""",
                [(c["user_id"], c["course_id"], c["current_step"], c["total_steps"],
                  c["completed"], c["started_at"], c["completed_at"], now)
                 for c in edu["courses"]],
            )
            total_courses += len(edu["courses"])

        if edu["challenges"]:
            await conn.executemany(
                """INSERT INTO challenge_enrollments
                   (user_id, challenge_id, status, start_date, end_date,
                    current_value, target_value, progress_pct, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)""",
                [(c["user_id"], c["challenge_id"], c["status"], c["start_date"], c["end_date"],
                  c["current_value"], c["target_value"], c["progress_pct"], now)
                 for c in edu["challenges"]],
            )
            total_challenges += len(edu["challenges"])

        if edu["badges"]:
            await conn.executemany(
                """INSERT INTO user_badges
                   (user_id, badge_name, badge_icon, description, challenge_id, earned_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $7)""",
                [(b["user_id"], b["badge_name"], b["badge_icon"], b["description"],
                  b["challenge_id"], b["earned_at"], now)
                 for b in edu["badges"]],
            )
            total_badges += len(edu["badges"])

        if edu["quizzes"]:
            await conn.executemany(
                """INSERT INTO quiz_scores
                   (user_id, quiz_type, score, total_questions, correct_count, taken_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $7)""",
                [(q["user_id"], q["quiz_type"], q["score"], q["total_questions"],
                  q["correct_count"], q["taken_at"], now)
                 for q in edu["quizzes"]],
            )
            total_quizzes += len(edu["quizzes"])

        # 리더보드 포인트
        quiz_avg = sum(q["score"] for q in edu["quizzes"]) / len(edu["quizzes"]) if edu["quizzes"] else 0
        n_completed_ch = sum(1 for c in edu["challenges"] if c["status"] == "completed")
        await conn.execute(
            """INSERT INTO leaderboard_points
               (user_id, total_points, badge_count, challenge_completed, quiz_score_avg, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $6)""",
            u["user_id"], edu["points"], len(edu["badges"]), n_completed_ch, round(quiz_avg, 1), now,
        )

    print(f"  -> 코스 진행: {total_courses}건")
    print(f"  -> 챌린지: {total_challenges}건")
    print(f"  -> 배지: {total_badges}건")
    print(f"  -> 퀴즈: {total_quizzes}건")

    # 통계 출력
    print("\n[7/7] 최종 통계 확인...")
    tables = ["users", "transactions", "spend_profile_cache", "budgets",
              "course_progress", "challenge_enrollments", "user_badges", "quiz_scores", "leaderboard_points"]
    print(f"\n{'테이블':<30} {'레코드 수':>10}")
    print("-" * 42)
    total = 0
    for t in tables:
        count = await conn.fetchval(f'SELECT COUNT(*) FROM "{t}"')
        print(f"  {t:<28} {count:>10,}")
        total += count
    print("-" * 42)
    print(f"  {'합계':<28} {total:>10,}")

    await conn.close()
    print(f"\n=== 시드 데이터 생성 완료! 총 {total:,}건 ===\n")


# ── 엔트리포인트 ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL 시드 데이터 생성")
    parser.add_argument("--users", type=int, default=20, help="사용자 수 (기본: 20)")
    parser.add_argument("--months", type=int, default=6, help="데이터 기간 (기본: 6개월)")
    parser.add_argument("--tx-per-month", type=int, default=60, help="월당 거래 수 (기본: 60)")
    args = parser.parse_args()

    asyncio.run(seed(args.users, args.months, args.tx_per_month))
