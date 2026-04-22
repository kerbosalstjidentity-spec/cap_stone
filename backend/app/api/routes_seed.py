"""데모 데이터 시드 API — 테스트용 거래 자동 생성."""

import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.tables import EmotionTag, Transaction
from app.schemas.spend import SpendCategory, TransactionIngest
from app.services.spend_profile import profile_store
from app.services.spend_profile_db import ingest_batch

# 감정 태그 생성용 매핑 — 카테고리×시간대 기반 현실적 감정 분포
_EMOTION_BY_CATEGORY: dict[SpendCategory, list[tuple[str, float]]] = {
    SpendCategory.FOOD: [("happy", 0.35), ("neutral", 0.30), ("stressed", 0.15), ("bored", 0.10), ("reward", 0.05), ("impulse", 0.05)],
    SpendCategory.SHOPPING: [("impulse", 0.25), ("happy", 0.20), ("reward", 0.20), ("stressed", 0.15), ("bored", 0.10), ("neutral", 0.10)],
    SpendCategory.ENTERTAINMENT: [("happy", 0.35), ("reward", 0.25), ("bored", 0.20), ("neutral", 0.10), ("impulse", 0.10)],
    SpendCategory.TRANSPORT: [("neutral", 0.70), ("stressed", 0.20), ("bored", 0.10)],
    SpendCategory.EDUCATION: [("neutral", 0.50), ("happy", 0.30), ("stressed", 0.20)],
    SpendCategory.HEALTHCARE: [("stressed", 0.50), ("neutral", 0.40), ("happy", 0.10)],
    SpendCategory.HOUSING: [("neutral", 0.60), ("stressed", 0.30), ("bored", 0.10)],
    SpendCategory.UTILITIES: [("neutral", 0.70), ("stressed", 0.20), ("bored", 0.10)],
    SpendCategory.FINANCE: [("neutral", 0.50), ("stressed", 0.25), ("happy", 0.15), ("reward", 0.10)],
    SpendCategory.TRAVEL: [("happy", 0.40), ("reward", 0.25), ("impulse", 0.15), ("neutral", 0.20)],
    SpendCategory.OTHER: [("neutral", 0.40), ("impulse", 0.20), ("bored", 0.20), ("stressed", 0.20)],
}


def _pick_emotion(cat: SpendCategory, hour: int) -> tuple[str, int]:
    """카테고리와 시간대에 기반하여 감정과 강도를 생성."""
    emotions_weights = _EMOTION_BY_CATEGORY.get(cat, [("neutral", 1.0)])
    emotions, weights = zip(*emotions_weights)
    # 심야(21-3시)엔 impulse/stressed 가중치 상향
    adj_weights = list(weights)
    if 21 <= hour or hour <= 3:
        for i, e in enumerate(emotions):
            if e in ("impulse", "stressed"):
                adj_weights[i] *= 2.0
    emotion = random.choices(emotions, weights=adj_weights, k=1)[0]
    # 강도: stressed/impulse는 3-5, happy/reward는 2-5, neutral/bored는 1-3
    if emotion in ("stressed", "impulse"):
        intensity = random.randint(3, 5)
    elif emotion in ("happy", "reward"):
        intensity = random.randint(2, 5)
    else:
        intensity = random.randint(1, 3)
    return emotion, intensity

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


async def seed_user_data(
    user_id: str,
    session: AsyncSession,
    months: int = 3,
    tx_per_month: int = 40,
    include_security: bool = True,
) -> dict:
    """사용자 데모 데이터 생성 헬퍼 — 거래 + 감정 + 보안 데이터.

    routes_auth.py 회원가입 후 자동 호출, routes_seed.py API 양쪽에서 사용.
    """
    txs = _generate_transactions(user_id, months, tx_per_month)

    # 인메모리 스토어
    for tx in txs:
        profile_store.ingest(tx)

    # DB 저장
    await ingest_batch(txs, session)

    # 감정 태그 (약 60%)
    emotion_count = 0
    for tx in txs:
        if random.random() < 0.6:
            hour = tx.timestamp.hour if tx.timestamp else 12
            emotion, intensity = _pick_emotion(tx.category, hour)
            tag = EmotionTag(
                user_id=user_id,
                transaction_id=tx.transaction_id,
                emotion=emotion,
                intensity=intensity,
                note="",
            )
            session.add(tag)
            emotion_count += 1
    await session.commit()

    # 보안 데이터 시딩 (MyData 동의, PID, 감사 로그)
    security_seeded = {}
    if include_security:
        security_seeded = await _seed_security_data(user_id, txs)

    profile = profile_store.get_profile(user_id)
    return {
        "status": "seeded",
        "user_id": user_id,
        "transactions_created": len(txs),
        "emotion_tags_created": emotion_count,
        "months": months,
        "total_amount": profile.total_amount if profile else 0,
        "categories": len(profile.category_breakdown) if profile else 0,
        **security_seeded,
    }


async def _seed_security_data(user_id: str, txs: list) -> dict:
    """보안 대시보드용 샘플 데이터 시딩 (인메모리 stores)."""
    import hashlib
    import json
    import secrets
    import time

    from app.api.routes_security_dashboard import (
        _AUDIT_CHAIN,
        _MYDATA_CONSENTS,
        _PID_REGISTRY,
    )

    # 1) 감사 로그 — 최근 거래 중 10건을 감사 체인에 기록
    audit_count = 0
    sample_txs = txs[-10:] if len(txs) >= 10 else txs
    for tx in sample_txs:
        ts = time.time() - random.uniform(0, 86400 * 7)
        actions = ["PASS", "PASS", "PASS", "SOFT_REVIEW", "REVIEW"]
        action = random.choice(actions)
        score = round(random.uniform(0.01, 0.3), 3) if action == "PASS" else round(random.uniform(0.5, 0.95), 3)
        prev_hash = _AUDIT_CHAIN[-1]["block_hash"] if _AUDIT_CHAIN else "0" * 64
        block = {
            "index": len(_AUDIT_CHAIN),
            "timestamp": ts,
            "transaction_id": tx.transaction_id,
            "user_id": user_id,
            "action": action,
            "score": score,
            "reason": f"FDS {action.lower()} — score {score}",
            "amount": tx.amount,
            "prev_hash": prev_hash,
            "block_hash": hashlib.sha256(
                json.dumps({"ts": ts, "tx": tx.transaction_id, "prev": prev_hash},
                           sort_keys=True).encode()
            ).hexdigest(),
        }
        _AUDIT_CHAIN.append(block)
        audit_count += 1

    # 2) MyData 동의 3건
    providers = [
        {"provider": "KB국민은행", "data_types": ["transactions", "balance"], "purpose": "spending_analysis"},
        {"provider": "신한카드", "data_types": ["transactions", "loan"], "purpose": "credit_score"},
        {"provider": "NH농협", "data_types": ["balance", "investment"], "purpose": "fds"},
    ]
    consents = []
    for p in providers:
        consent = {
            "consent_id": secrets.token_hex(8),
            "provider": p["provider"],
            "data_types": p["data_types"],
            "purpose": p["purpose"],
            "granted_at": time.time() - random.randint(86400, 86400 * 30),
            "expires_at": time.time() + 365 * 86400,
            "status": "active",
        }
        consents.append(consent)
    _MYDATA_CONSENTS[user_id] = consents

    # 3) PID 생성
    pid = hashlib.sha256(
        f"PID:{user_id}:{time.time()}:{secrets.token_hex(8)}".encode()
    ).hexdigest()[:16]
    _PID_REGISTRY[user_id] = {
        "pid": f"PID-{pid}",
        "real_user_id": user_id,
        "created_at": time.time(),
        "rotation_at": time.time() + 90 * 86400,
        "rotation_days": 90,
        "version": 1,
        "history": [],
    }

    return {
        "audit_logs_created": audit_count,
        "mydata_consents_created": len(consents),
        "pid_generated": True,
    }


@router.post("/demo/{user_id}")
async def seed_demo_data(
    user_id: str,
    months: int = 3,
    tx_per_month: int = 40,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """데모 거래 데이터를 자동 생성하여 DB + 인메모리 스토어에 저장."""
    # 기존 데이터 초기화
    profile_store.delete_user(user_id)
    await session.execute(delete(EmotionTag).where(EmotionTag.user_id == user_id))
    await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await session.commit()

    return await seed_user_data(user_id, session, months, tx_per_month)


@router.delete("/reset/{user_id}")
async def reset_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """사용자 데이터 초기화."""
    profile_store.delete_user(user_id)
    result = await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await session.commit()
    deleted = result.rowcount > 0
    return {"status": "reset" if deleted else "not_found", "user_id": user_id}
