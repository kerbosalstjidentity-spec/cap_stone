"""W8-#6 — OR 결합 false-positive 비용 평가.

룰 엔진의 ``OR`` 결합은 recall ↑ 효과가 있지만 각 룰의 FP 가 합산되어
운영 비용 (고객 마찰, CS 처리비)이 증가한다. 본 모듈은:

1. 룰별 (true_positive_rate, false_positive_rate, trigger_count) 입력
2. OR 결합 시 결합 FP 추정 — naive independence:
       P_FP_OR = 1 - Π(1 - fp_i)
3. AND 결합 vs OR 결합 expected_cost 비교
4. ``recommend_threshold`` — FP 비용 임계 초과 시 룰 disable 권고

scipy 미의존. 운영 환경에서 ``stats_collector`` 의 triggered_rules + chargeback
piggy back 으로 룰별 통계 산출 후 본 함수에 주입.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RuleStat:
    rule_id: str
    fp_rate: float        # 0~1
    tp_rate: float        # 0~1
    trigger_count: int    # 누적 트리거 수
    cost_per_fp_krw: float = 5000.0  # CS 처리비 + 기회비용 추정


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def or_fp_combined(rules: list[RuleStat]) -> float:
    """OR 결합 시 결합 FP 확률 (독립 가정)."""
    if not rules:
        return 0.0
    product = 1.0
    for r in rules:
        product *= (1.0 - _clip(r.fp_rate))
    return 1.0 - product


def expected_fp_count_per_day(
    rules: list[RuleStat],
    daily_traffic: int,
) -> dict:
    """일 트래픽 N 가정하 룰별·OR 결합 FP 건수/비용 추정."""
    per_rule = []
    or_combined_rate = or_fp_combined(rules)
    total_cost = 0.0
    total_fp = 0
    for r in rules:
        fp_per_day = int(round(daily_traffic * _clip(r.fp_rate)))
        cost = fp_per_day * max(0.0, r.cost_per_fp_krw)
        total_fp += fp_per_day
        total_cost += cost
        per_rule.append({
            "rule_id": r.rule_id,
            "fp_rate": round(_clip(r.fp_rate), 4),
            "tp_rate": round(_clip(r.tp_rate), 4),
            "fp_per_day": fp_per_day,
            "cost_krw_per_day": round(cost, 2),
        })

    or_fp_per_day = int(round(daily_traffic * or_combined_rate))
    return {
        "daily_traffic": daily_traffic,
        "per_rule": per_rule,
        "sum_fp_naive": total_fp,        # 룰별 단순 합 (중복 포함)
        "sum_cost_naive_krw": round(total_cost, 2),
        "or_combined_fp_rate": round(or_combined_rate, 4),
        "or_combined_fp_per_day": or_fp_per_day,
    }


def recommend_disable(
    rules: list[RuleStat],
    *,
    max_cost_share: float = 0.4,
    min_tp_rate: float = 0.10,
) -> list[dict]:
    """비용 점유율 ``max_cost_share`` 이상이면서 TP rate < ``min_tp_rate`` 인 룰 권고.

    "비싸기만 하고 안 잡는 룰" 우선 disable 후보.
    """
    if not rules:
        return []
    total_cost = sum(_clip(r.fp_rate) * r.cost_per_fp_krw * r.trigger_count for r in rules) or 1.0
    out = []
    for r in rules:
        cost = _clip(r.fp_rate) * r.cost_per_fp_krw * r.trigger_count
        share = cost / total_cost
        if share >= max_cost_share and _clip(r.tp_rate) < min_tp_rate:
            out.append({
                "rule_id": r.rule_id,
                "cost_share": round(share, 4),
                "tp_rate": round(_clip(r.tp_rate), 4),
                "fp_rate": round(_clip(r.fp_rate), 4),
                "reason": "high_cost_low_tp",
            })
    return out


def kappa_redundancy(rules: list[RuleStat]) -> float:
    """OR 결합 시 룰 간 중복도(0~1). 1에 가까울수록 같은 케이스만 잡아 비효율."""
    n = len(rules)
    if n <= 1:
        return 0.0
    or_rate = or_fp_combined(rules)
    independent_max = 1.0 - math.prod((1.0 - _clip(r.fp_rate)) for r in rules)
    sum_rate = sum(_clip(r.fp_rate) for r in rules)
    if sum_rate == 0:
        return 0.0
    # 룰들이 완전 독립이면 or_rate ≈ independent_max, 완전 중첩이면 or_rate ≈ max(fp_i)
    # redundancy = (sum - or_rate) / sum  ∈ [0, 1)
    return round(max(0.0, min(1.0, (sum_rate - or_rate) / sum_rate)), 4)
