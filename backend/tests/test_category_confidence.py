"""W5-#6 — 카테고리 분류 confidence score 테스트."""
from __future__ import annotations

from app.schemas.spend import SpendCategory
from app.services.category_engine import classify_with_confidence


def test_mcc_match_high_confidence():
    out = classify_with_confidence(mcc=5811)  # 레스토랑
    assert out["category"] == SpendCategory.FOOD
    assert out["confidence"] == 0.95
    assert out["source"] == "mcc"


def test_keyword_match_partial_confidence():
    out = classify_with_confidence(text="스타벅스 강남점 결제")
    assert out["category"] == SpendCategory.FOOD
    assert 0.5 <= out["confidence"] < 0.95
    assert out["source"] == "keyword"
    assert "스타벅스" in out["matched_keywords"]


def test_keyword_full_match_high_confidence():
    out = classify_with_confidence(text="스타벅스")
    assert out["category"] == SpendCategory.FOOD
    assert out["confidence"] >= 0.9


def test_no_match_zero_confidence():
    out = classify_with_confidence(text="알수없는가맹점")
    assert out["category"] == SpendCategory.OTHER
    assert out["confidence"] == 0.0
    assert out["source"] == "fallback"


def test_empty_input_zero():
    out = classify_with_confidence()
    assert out["confidence"] == 0.0
    assert out["category"] == SpendCategory.OTHER


def test_mcc_priority_over_keyword():
    # MCC 가 비-OTHER 면 키워드는 안 본다
    out = classify_with_confidence(mcc=5811, text="스타벅스")
    assert out["source"] == "mcc"
    assert out["confidence"] == 0.95
