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
    "BALANCE_DRAIN",
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
    "BALANCE_DRAIN": "계좌 자금 인출 의심",
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
    # W6.5-#3/#4: 그래프 기반 머니뮬·layering 룰이 발동하면 최우선 라벨
    if "MONEY_MULE_HUB" in s or "LAYERING_CHAIN" in s:
        return "MONEY_MULE"
    # W7.5-#1: 잔액 급변 — 그래프 신호 부재 시 단독 라벨
    if "BALANCE_DRAIN" in s:
        return "BALANCE_DRAIN"
    if "SPLIT_TXN" in s:
        return "CARD_TESTING"
    if "VELOCITY_FREQ" in s and not (s & _AMOUNT_RULES):
        return "CARD_TESTING"
    if s & {"FOREIGN_IP", "DEVICE_FINGERPRINT", "OFF_HOURS_CLUSTER"}:
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


# ---------------------------------------------------------------------------
# W6.5-#6 — fraud_type 별 차등 임계값
# ---------------------------------------------------------------------------

# fraud_type 이 식별된 거래에서 모델 score 가 이 임계 이상이면 BLOCK 으로 승격.
# 룰 시그널이 강한 유형(MONEY_MULE/CARD_TESTING)은 낮은 score 에서도 신뢰 →
# false-negative 감소. 룰 시그널이 약한 유형(AMOUNT_ANOMALY)은 보수적.
# NORMAL 은 1.01 (절대 트리거 안 됨, 안전 default).
FRAUD_TYPE_BLOCK_THRESHOLDS: dict[str, float] = {
    "BLACKLIST":         0.0,    # 블랙리스트 일치 즉시 BLOCK
    "MONEY_MULE":        0.5,    # 그래프 시그널 강함
    "CARD_TESTING":      0.7,    # 룰 시그널 강함
    "VOICE_PHISHING":    0.6,    # 야간+고액 시그널
    "ACCOUNT_TAKEOVER":  0.65,   # 해외IP/디바이스 시그널
    "AMOUNT_ANOMALY":    0.85,   # 금액만 — 보수적
    "BALANCE_DRAIN":     0.55,   # W7.5-#1 — 잔액 90%↑ 드레인 시그널 강함
    "NORMAL":            1.01,   # 룰 미발동 — 차등 적용 안 함
}


def apply_fraud_type_threshold(action: str, score: float, fraud_type: str) -> str:
    """W6.5-#6 — fraud_type 식별된 거래에서 score 가 유형별 임계 이상이면 BLOCK.

    이미 BLOCK 이거나 NORMAL 유형이면 변화 없음. REVIEW/SOFT_REVIEW/PASS 가
    임계 통과 시 BLOCK 으로 승격.

    Args:
        action: 현재 final_action (score+rule+cost merge 결과)
        score: 모델 score (0~1)
        fraud_type: classify_fraud_type 결과
    """
    if action == "BLOCK":
        return action
    threshold = FRAUD_TYPE_BLOCK_THRESHOLDS.get(fraud_type, 1.01)
    if score >= threshold:
        return "BLOCK"
    return action
