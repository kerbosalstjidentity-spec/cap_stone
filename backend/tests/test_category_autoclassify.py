"""W9-#9 — 카테고리 ingest 경로 wiring + 키워드 우선순위 테스트.

DB 의존(ingest_transaction) 회피 위해 _autoclassify_if_other 헬퍼와
classify() 만 직접 호출.
"""
from __future__ import annotations

from app.schemas.spend import SpendCategory, TransactionIngest
from app.services.category_engine import classify, _KEYWORD_MAP
from app.services.spend_profile_db import _autoclassify_if_other


def _tx(category: SpendCategory, merchant_id: str = "", memo: str = "") -> TransactionIngest:
    from datetime import datetime, timezone
    return TransactionIngest(
        transaction_id="t1",
        user_id="u1",
        amount=1000.0,
        timestamp=datetime.now(tz=timezone.utc),
        merchant_id=merchant_id,
        category=category,
        channel="card",
        is_domestic=True,
        memo=memo,
    )


def test_keeps_explicit_non_other_category():
    tx = _tx(SpendCategory.FOOD, merchant_id="아무거나")
    assert _autoclassify_if_other(tx) == SpendCategory.FOOD


def test_classifies_when_other_with_keyword():
    tx = _tx(SpendCategory.OTHER, merchant_id="스타벅스 강남점")
    assert _autoclassify_if_other(tx) == SpendCategory.FOOD


def test_classifies_from_memo():
    tx = _tx(SpendCategory.OTHER, merchant_id="ABC123", memo="넷플릭스 구독")
    assert _autoclassify_if_other(tx) == SpendCategory.ENTERTAINMENT


def test_other_when_no_text():
    tx = _tx(SpendCategory.OTHER, merchant_id="", memo="")
    assert _autoclassify_if_other(tx) == SpendCategory.OTHER


def test_keyword_priority_first_match_wins():
    """삽입 순서대로 첫 매칭 키워드가 이긴다 — 복합 가맹점명 동작 확인."""
    # 배달의민족이 dict 위쪽, 쿠팡이 아래쪽 → 복합 시 FOOD 선택
    keywords = list(_KEYWORD_MAP.keys())
    assert keywords.index("배달의민족") < keywords.index("쿠팡")
    assert classify(text="배달의민족_쿠팡마트") == SpendCategory.FOOD


def test_keyword_case_insensitive():
    assert classify(text="STARBUCKS 강남") == SpendCategory.OTHER  # "STARBUCKS" 아닌 "스타벅스" 만 매칭
    assert classify(text="스타벅스 STARBUCKS") == SpendCategory.FOOD
