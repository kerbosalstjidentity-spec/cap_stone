"""MCC 코드 → SpendCategory 매핑 엔진."""

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
