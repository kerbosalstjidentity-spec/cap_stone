"""MCC 코드 → SpendCategory 매핑 엔진.

W9-#9: 키워드 매칭 우선순위는 ``_KEYWORD_MAP`` 의 **삽입 순서**.
파이썬 dict 는 3.7+ 이후 순서를 보존하므로 첫 번째 매칭 키워드가 이긴다.
복합 가맹점명(예: "배달의민족_쿠팡마트")은 dict 위쪽 키워드(``배달의민족``)가
먼저 매칭되어 FOOD 로 분류 — 모호함을 피하려면 더 구체적인 브랜드를 위에
배치할 것. 향후 확장 시 ``(keyword, priority, category)`` 튜플 + 정렬 리스트
로 마이그레이션 권장.
"""

from app.schemas.spend import SpendCategory

# MCC 코드 범위 → 카테고리 매핑 (한국 기준 주요 업종)
_MCC_MAP: dict[range, SpendCategory] = {
    range(5811, 5815): SpendCategory.FOOD,         # 레스토랑/카페
    range(5411, 5500): SpendCategory.FOOD,         # 식료품/마트
    range(5200, 5400): SpendCategory.SHOPPING,     # 의류/잡화
    range(5600, 5700): SpendCategory.SHOPPING,     # 의류
    range(5900, 6000): SpendCategory.SHOPPING,     # 기타 소매
    range(4011, 4800): SpendCategory.TRANSPORT,    # 교통/항공
    range(7800, 7999): SpendCategory.ENTERTAINMENT,# 영화/공연/게임
    range(7911, 7942): SpendCategory.ENTERTAINMENT,# 오락/레저
    range(8200, 8300): SpendCategory.EDUCATION,    # 교육
    range(8000, 8100): SpendCategory.HEALTHCARE,   # 의료
    range(6000, 6200): SpendCategory.FINANCE,      # 금융/보험
    range(3000, 3500): SpendCategory.TRAVEL,       # 항공/호텔
    range(7000, 7300): SpendCategory.TRAVEL,       # 숙박/렌터카
    range(4900, 5000): SpendCategory.UTILITIES,    # 공과금/통신
}

# 키워드 기반 fallback (merchant_id 또는 memo 에서)
_KEYWORD_MAP: dict[str, SpendCategory] = {
    "스타벅스": SpendCategory.FOOD,
    "이디야": SpendCategory.FOOD,
    "배달의민족": SpendCategory.FOOD,
    "쿠팡": SpendCategory.SHOPPING,
    "네이버쇼핑": SpendCategory.SHOPPING,
    "카카오택시": SpendCategory.TRANSPORT,
    "넷플릭스": SpendCategory.ENTERTAINMENT,
    "병원": SpendCategory.HEALTHCARE,
    "약국": SpendCategory.HEALTHCARE,
    "교보문고": SpendCategory.EDUCATION,
    "학원": SpendCategory.EDUCATION,
    "전기료": SpendCategory.UTILITIES,
    "KT": SpendCategory.UTILITIES,
    "SKT": SpendCategory.UTILITIES,
}


def classify_by_mcc(mcc: int) -> SpendCategory:
    for mcc_range, cat in _MCC_MAP.items():
        if mcc in mcc_range:
            return cat
    return SpendCategory.OTHER


def classify_by_keyword(text: str) -> SpendCategory:
    text_lower = text.lower()
    for keyword, cat in _KEYWORD_MAP.items():
        if keyword.lower() in text_lower:
            return cat
    return SpendCategory.OTHER


def classify(mcc: int | None = None, text: str = "") -> SpendCategory:
    if mcc is not None:
        result = classify_by_mcc(mcc)
        if result != SpendCategory.OTHER:
            return result
    if text:
        return classify_by_keyword(text)
    return SpendCategory.OTHER


# W5-#6: 분류 신뢰도 (confidence) — 다운스트림 (감정 분석/추천 가중치) 에서
# 자신 없는 분류는 weight 를 낮추도록.
#
# 신뢰도 산출 규칙 (단순/투명):
#   - MCC 매칭으로 비-OTHER 분류 → 0.95 (가장 신뢰)
#   - 키워드 매칭으로 비-OTHER → 매칭된 키워드 길이/텍스트 길이 비율 기반:
#       완전 일치(키워드==텍스트)에 가까울수록 1.0, 텍스트가 길수록 0.5~0.8
#   - 다중 키워드 매칭 시 매칭 개수 +0.05 가산 (cap 0.95)
#   - OTHER → 0.0 (분류 실패 = 신뢰 0)
def _keyword_confidence(text: str) -> tuple[SpendCategory, float, list[str]]:
    text_lower = text.lower()
    matched: list[str] = []
    first: SpendCategory | None = None
    for keyword, cat in _KEYWORD_MAP.items():
        if keyword.lower() in text_lower:
            matched.append(keyword)
            if first is None:
                first = cat
    if first is None:
        return SpendCategory.OTHER, 0.0, []
    # 첫 매칭 키워드 길이 / 텍스트 길이 ∈ (0,1]
    first_kw_len = len(matched[0])
    text_len = max(1, len(text.strip()))
    base = min(0.95, max(0.5, first_kw_len / text_len))
    bonus = min(0.95 - base, 0.05 * (len(matched) - 1))
    return first, round(base + bonus, 4), matched


def classify_with_confidence(
    mcc: int | None = None, text: str = ""
) -> dict:
    """W5-#6: 카테고리 + confidence + source + matched_keywords 반환."""
    if mcc is not None:
        cat = classify_by_mcc(mcc)
        if cat != SpendCategory.OTHER:
            return {
                "category": cat,
                "confidence": 0.95,
                "source": "mcc",
                "matched_keywords": [],
            }
    if text:
        cat, conf, matched = _keyword_confidence(text)
        return {
            "category": cat,
            "confidence": conf,
            "source": "keyword" if matched else "fallback",
            "matched_keywords": matched,
        }
    return {
        "category": SpendCategory.OTHER,
        "confidence": 0.0,
        "source": "fallback",
        "matched_keywords": [],
    }
