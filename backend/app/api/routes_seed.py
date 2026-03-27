"""데모 데이터 시드 API — 테스트용 거래 자동 생성."""

import random
from datetime import datetime, timedelta

from fastapi import APIRouter

from app.schemas.spend import SpendCategory, TransactionIngest
from app.services.spend_profile import profile_store

router = APIRouter(prefix="/v1/seed", tags=["seed"])

_MERCHANTS = {
    SpendCategory.FOOD: ["스타벅스_강남", "배달의민족_주문", "이마트_식품", "맘스터치_논현", "CU편의점"],
    SpendCategory.SHOPPING: ["쿠팡_배송", "네이버쇼핑", "올리브영_홍대", "무신사_의류", "다이소_잡화"],
    SpendCategory.TRANSPORT: ["카카오택시", "서울교통공사", "쏘카_렌트", "주유소_SK", "고속버스"],
    SpendCategory.ENTERTAINMENT: ["넷플릭스", "CGV_영화", "스포티파이", "PC방_게임", "노래방"],
    SpendCategory.EDUCATION: ["교보문고", "인프런_강의", "학원비_수학", "유데미_온라인"],
    SpendCategory.HEALTHCARE: ["서울대병원", "올리브약국", "헬스장_PT"],
    SpendCategory.HOUSING: ["월세_이체", "관리비"],
    SpendCategory.UTILITIES: ["KT_통신비", "한전_전기료", "서울시_수도"],
    SpendCategory.FINANCE: ["적금_이체", "보험료_납부"],
    SpendCategory.TRAVEL: ["대한항공", "호텔_예약", "여행자보험"],
}

_AMOUNT_RANGES: dict[SpendCategory, tuple[int, int]] = {
    SpendCategory.FOOD: (3000, 50000),
    SpendCategory.SHOPPING: (5000, 200000),
    SpendCategory.TRANSPORT: (1200, 30000),
    SpendCategory.ENTERTAINMENT: (5000, 30000),
    SpendCategory.EDUCATION: (10000, 100000),
    SpendCategory.HEALTHCARE: (5000, 150000),
    SpendCategory.HOUSING: (300000, 800000),
    SpendCategory.UTILITIES: (20000, 100000),
    SpendCategory.FINANCE: (100000, 500000),
    SpendCategory.TRAVEL: (50000, 500000),
}

# 카테고리별 월간 발생 확률 (가중치)
_CATEGORY_WEIGHTS = {
    SpendCategory.FOOD: 35,
    SpendCategory.SHOPPING: 20,
    SpendCategory.TRANSPORT: 15,
    SpendCategory.ENTERTAINMENT: 8,
    SpendCategory.EDUCATION: 5,
    SpendCategory.HEALTHCARE: 3,
    SpendCategory.HOUSING: 2,
    SpendCategory.UTILITIES: 4,
    SpendCategory.FINANCE: 3,
    SpendCategory.TRAVEL: 2,
    SpendCategory.OTHER: 3,
}


def _generate_transactions(user_id: str, months: int = 3, tx_per_month: int = 40) -> list[TransactionIngest]:
    """지정 기간만큼 현실적인 거래 데이터 생성."""
    txs: list[TransactionIngest] = []
    now = datetime.now()
    categories = list(_CATEGORY_WEIGHTS.keys())
    weights = list(_CATEGORY_WEIGHTS.values())

    for month_offset in range(months, 0, -1):
        base_date = now - timedelta(days=month_offset * 30)
        # 월별 거래 수에 약간의 변동
        count = tx_per_month + random.randint(-5, 5)

        for j in range(count):
            cat = random.choices(categories, weights=weights, k=1)[0]
            day_offset = random.randint(0, 29)
            hour = random.choices(
                range(24),
                weights=[1, 1, 1, 1, 1, 2, 3, 5, 6, 5, 4, 8, 12, 8, 6, 5, 5, 7, 10, 8, 5, 3, 2, 1],
                k=1,
            )[0]
            minute = random.randint(0, 59)

            ts = base_date + timedelta(days=day_offset, hours=hour, minutes=minute)

            lo, hi = _AMOUNT_RANGES.get(cat, (1000, 50000))
            amount = round(random.randint(lo, hi) / 100) * 100  # 100원 단위

            merchants = _MERCHANTS.get(cat, ["기타_가맹점"])
            merchant = random.choice(merchants)

            # 가끔 이상 거래 삽입 (약 2%)
            if random.random() < 0.02:
                amount = amount * random.randint(5, 10)

            channels = ["app", "app", "app", "web", "offline"]

            txs.append(
                TransactionIngest(
                    transaction_id=f"seed_{user_id}_{month_offset}_{j:04d}",
                    user_id=user_id,
                    amount=float(amount),
                    timestamp=ts,
                    merchant_id=merchant,
                    category=cat if cat != SpendCategory.OTHER else SpendCategory.OTHER,
                    channel=random.choice(channels),
                    is_domestic=random.random() > 0.05,
                    memo=merchant,
                )
            )

    return sorted(txs, key=lambda t: t.timestamp)


@router.post("/demo/{user_id}")
async def seed_demo_data(user_id: str, months: int = 3, tx_per_month: int = 40) -> dict:
    """데모 거래 데이터를 자동 생성하여 프로필에 주입.

    Args:
        user_id: 사용자 ID
        months: 생성할 개월 수 (기본 3개월)
        tx_per_month: 월당 거래 수 (기본 40)
    """
    txs = _generate_transactions(user_id, months, tx_per_month)
    for tx in txs:
        profile_store.ingest(tx)

    profile = profile_store.get_profile(user_id)
    return {
        "status": "seeded",
        "user_id": user_id,
        "transactions_created": len(txs),
        "months": months,
        "total_amount": profile.total_amount if profile else 0,
        "categories": len(profile.category_breakdown) if profile else 0,
    }


@router.delete("/reset/{user_id}")
async def reset_user(user_id: str) -> dict:
    """사용자 데이터 초기화."""
    deleted = profile_store.delete_user(user_id)
    return {"status": "reset" if deleted else "not_found", "user_id": user_id}
