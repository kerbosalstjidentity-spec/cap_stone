"""규칙 조치와 모델 밴드를 합성 (더 강한 쪽 우선)."""

from __future__ import annotations

ACTION_RANK = {"PASS": 0, "REVIEW": 1, "BLOCK": 2}
RANK_TO_ACTION = {0: "PASS", 1: "REVIEW", 2: "BLOCK"}


def decide_from_score(score: float, block_min: float, review_min: float, adjustments: list = None, row: dict = None) -> str:
    adjusted_score = score
    if adjustments and row:
        for adj in adjustments:
            condition = adj['condition']
            # 간단 조건 파싱 (V2 > 5.0 등)
            try:
                var, op, val = condition.split()
                var_val = float(row.get(var, 0))
                val = float(val)
                if op == '>' and var_val > val:
                    adjusted_score += adj['score_adjust']
                elif op == '<' and var_val < val:
                    adjusted_score += adj['score_adjust']
                # and 조건 추가 가능
            except:
                pass  # 무시
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
