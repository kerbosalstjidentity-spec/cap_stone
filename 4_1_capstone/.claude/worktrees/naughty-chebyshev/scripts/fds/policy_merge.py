"""규칙 조치와 모델 밴드를 합성 (더 강한 쪽 우선)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

ACTION_RANK = {"PASS": 0, "REVIEW": 1, "BLOCK": 2}
RANK_TO_ACTION = {0: "PASS", 1: "REVIEW", 2: "BLOCK"}

# 단일 조건 패턴: "V2 > 5.0" 형태
_SINGLE_COND_RE = re.compile(r"^\s*(\w+)\s*(>|<|>=|<=|==|!=)\s*(-?[\d.]+)\s*$")


def _eval_single(condition: str, row: dict) -> bool:
    """'VAR OP NUM' 단일 조건을 평가한다. 파싱 실패 시 False 반환."""
    m = _SINGLE_COND_RE.match(condition)
    if not m:
        logger.warning("조건 파싱 실패 (단일 조건 형식 아님): %r", condition)
        return False
    var, op, val_str = m.group(1), m.group(2), m.group(3)
    var_val = row.get(var)
    if var_val is None:
        return False
    try:
        lhs = float(var_val)
        rhs = float(val_str)
    except (ValueError, TypeError):
        return False
    return {
        ">": lhs > rhs,
        "<": lhs < rhs,
        ">=": lhs >= rhs,
        "<=": lhs <= rhs,
        "==": lhs == rhs,
        "!=": lhs != rhs,
    }[op]


def _eval_condition(condition: str, row: dict) -> bool:
    """
    조건 문자열을 평가한다.
    - 단일: "V2 > 5.0"
    - and 결합: "V1 < -4.0 and V3 < -2.0"
    모든 항목이 True여야 전체가 True.
    """
    parts = re.split(r"\band\b", condition, flags=re.IGNORECASE)
    return all(_eval_single(p.strip(), row) for p in parts)


def decide_from_score(
    score: float,
    block_min: float,
    review_min: float,
    adjustments: list | None = None,
    row: dict | None = None,
) -> str:
    adjusted_score = score
    if adjustments and row:
        for adj in adjustments:
            condition = adj.get("condition", "")
            try:
                if _eval_condition(condition, row):
                    adjusted_score += float(adj["score_adjust"])
            except Exception as e:
                logger.warning("조정 항목 처리 오류 (condition=%r): %s", condition, e)
    if adjusted_score >= block_min:
        return "BLOCK"
    if adjusted_score >= review_min:
        return "REVIEW"
    return "PASS"


def merge_actions(rule_action: str, model_action: str) -> str:
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
