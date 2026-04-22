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
