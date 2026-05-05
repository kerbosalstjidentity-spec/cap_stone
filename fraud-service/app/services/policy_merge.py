"""규칙 조치와 모델 밴드를 합성 (더 강한 쪽 우선) — capstone policy_merge.py 이식."""

from __future__ import annotations

ACTION_RANK = {"PASS": 0, "SOFT_REVIEW": 1, "REVIEW": 2, "BLOCK": 3}
RANK_TO_ACTION = {0: "PASS", 1: "SOFT_REVIEW", 2: "REVIEW", 3: "BLOCK"}


def merge_actions(rule_action: str, model_action: str) -> str:
    """두 action 중 더 강한 쪽을 반환."""
    r = ACTION_RANK.get(rule_action, 0)
    m = ACTION_RANK.get(model_action, 0)
    return RANK_TO_ACTION[max(r, m)]


def audit_summary(reason_code: str, rule_ids: str) -> str:
    parts = []
    if reason_code:
        parts.append(f"model:{reason_code}")
    if rule_ids:
        parts.append(f"rules:{rule_ids}")
    return " | ".join(parts) if parts else ""


def evaluate_amount_rule(amount: float, *, block_threshold: float, review_threshold: float) -> tuple[str, str]:
    """
    금액 기반 단순 규칙 평가.
    Returns: (rule_action, rule_id)
    """
    if amount >= block_threshold:
        return "BLOCK", "AMOUNT_BLOCK"
    if amount >= review_threshold:
        return "REVIEW", "AMOUNT_REVIEW"
    return "PASS", ""


# ---------------------------------------------------------------------------
# W5.5-#5 — 사기 유형 다중분류 (fraud_type)
# ---------------------------------------------------------------------------

FRAUD_TYPES = (
    "VOICE_PHISHING",
    "MONEY_MULE",
    "ACCOUNT_TAKEOVER",
    "CARD_TESTING",
    "AMOUNT_ANOMALY",
    "BLACKLIST",
    "NORMAL",
)

# 한국어 라벨 — XAI Reason Code 와 결합해 사용자 메시지에 활용
FRAUD_TYPE_LABELS_KO: dict[str, str] = {
    "VOICE_PHISHING": "보이스피싱 의심",
    "MONEY_MULE": "머니뮬(자금 세탁) 의심",
    "ACCOUNT_TAKEOVER": "계정 탈취 의심",
    "CARD_TESTING": "카드 테스팅 공격 의심",
    "AMOUNT_ANOMALY": "비정상 금액 패턴",
    "BLACKLIST": "블랙리스트 일치",
    "NORMAL": "정상",
}

_AMOUNT_RULES = {"AMOUNT_BLOCK", "AMOUNT_REVIEW"}
_ANOMALY_RULES = {"AMOUNT_BLOCK", "AMOUNT_REVIEW", "AMOUNT_SPIKE", "NEW_MERCHANT"}


def classify_fraud_type(rule_ids: list[str] | str | None) -> str:
    """발동 룰 집합 → ``fraud_type`` 라벨.

    매핑 우선순위 (구체적 → 일반적):
        1. ``BLACKLIST`` 단독 → BLACKLIST
        2. ``SPLIT_TXN`` 또는 (``VELOCITY_FREQ`` 단독) → CARD_TESTING
        3. ``FOREIGN_IP`` 또는 ``DEVICE_FINGERPRINT`` → ACCOUNT_TAKEOVER
        4. ``VELOCITY_FREQ`` + 금액 룰 → MONEY_MULE
        5. ``TIME_RISK`` + 금액 룰 → VOICE_PHISHING
        6. 금액·이상치 계열만 → AMOUNT_ANOMALY
        7. 룰 없음 → NORMAL

    Args:
        rule_ids: ``rule_engine.get_strongest`` 의 콤마 구분 문자열 또는 list.
    """
    if not rule_ids:
        return "NORMAL"
    if isinstance(rule_ids, str):
        ids = [r.strip() for r in rule_ids.split(",") if r.strip()]
    else:
        ids = [r for r in rule_ids if r]
    s = set(ids)

    if "BLACKLIST" in s:
        return "BLACKLIST"
    # W6.5-#3: 그래프 기반 머니뮬 룰이 발동하면 최우선 라벨
    if "MONEY_MULE_HUB" in s:
        return "MONEY_MULE"
    if "SPLIT_TXN" in s:
        return "CARD_TESTING"
    if "VELOCITY_FREQ" in s and not (s & _AMOUNT_RULES):
        return "CARD_TESTING"
    if s & {"FOREIGN_IP", "DEVICE_FINGERPRINT"}:
        return "ACCOUNT_TAKEOVER"
    if "VELOCITY_FREQ" in s and (s & _AMOUNT_RULES):
        return "MONEY_MULE"
    if "TIME_RISK" in s and (s & _AMOUNT_RULES):
        return "VOICE_PHISHING"
    if s & _ANOMALY_RULES:
        return "AMOUNT_ANOMALY"
    return "NORMAL"


def fraud_type_label_ko(fraud_type: str) -> str:
    """``fraud_type`` 키 → 한국어 라벨."""
    return FRAUD_TYPE_LABELS_KO.get(fraud_type, fraud_type)
