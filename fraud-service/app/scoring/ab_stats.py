"""W7-#7 — A/B 통계적 유의성 검정 (chi-square / 2-proportion z-test).

scipy 미의존. ab_test.get_stats() 의 누적 카운트로:
- 두 변종(a, b) 간 BLOCK 비율 차이의 z-test (정규 근사 CDF — math.erf)
- BLOCK/REVIEW/PASS 3분할 카이제곱 통계량 (df=2)

판정: ``p_value < 0.05`` 면 ``significant`` True.
"""

from __future__ import annotations

import math


def _phi(z: float) -> float:
    """표준 정규 분포 CDF — Φ(z)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_proportion_z_test(
    succ_a: int, n_a: int, succ_b: int, n_b: int
) -> dict:
    """두 모집단의 비율 차이 양측 z-test."""
    if n_a <= 0 or n_b <= 0:
        return {
            "p_a": 0.0, "p_b": 0.0,
            "z": 0.0, "p_value": 1.0, "significant": False,
            "note": "표본 부족",
        }
    p_a = succ_a / n_a
    p_b = succ_b / n_b
    pooled = (succ_a + succ_b) / (n_a + n_b)
    denom_sq = pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b)
    if denom_sq <= 0:
        return {
            "p_a": round(p_a, 6), "p_b": round(p_b, 6),
            "z": 0.0, "p_value": 1.0, "significant": False,
            "note": "분산 0",
        }
    z = (p_a - p_b) / math.sqrt(denom_sq)
    # 양측 p-value
    p_value = 2.0 * (1.0 - _phi(abs(z)))
    return {
        "p_a": round(p_a, 6),
        "p_b": round(p_b, 6),
        "z": round(z, 4),
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
    }


def _chi2_pvalue_df2(chi2: float) -> float:
    """카이제곱 분포(df=2) 의 우측 p-value = exp(-chi2/2). df=2 한정 closed form."""
    if chi2 <= 0:
        return 1.0
    return math.exp(-chi2 / 2.0)


def chi_square_3way(stats_a: dict, stats_b: dict) -> dict:
    """BLOCK/REVIEW/PASS 3분할 카이제곱 통계량 (df=2).

    stats: {"block": int, "review": int, "pass": int, ...} (ab_test.get_stats 의 형식)
    """
    cats = ["block", "review", "pass"]
    a_obs = [int(stats_a.get(c, 0)) for c in cats]
    b_obs = [int(stats_b.get(c, 0)) for c in cats]
    n_a = sum(a_obs)
    n_b = sum(b_obs)
    if n_a == 0 or n_b == 0:
        return {"chi2": 0.0, "df": 2, "p_value": 1.0,
                "significant": False, "note": "표본 부족"}
    total = n_a + n_b
    chi2 = 0.0
    for i in range(3):
        col_total = a_obs[i] + b_obs[i]
        if col_total == 0:
            continue
        e_a = n_a * col_total / total
        e_b = n_b * col_total / total
        if e_a > 0:
            chi2 += (a_obs[i] - e_a) ** 2 / e_a
        if e_b > 0:
            chi2 += (b_obs[i] - e_b) ** 2 / e_b
    p_value = _chi2_pvalue_df2(chi2)
    return {
        "chi2": round(chi2, 4),
        "df": 2,
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
        "n_a": n_a,
        "n_b": n_b,
    }


def compute_significance(stats: dict | None = None) -> dict:
    """ab_test.get_stats() 결과를 받아 BLOCK 비율 z-test + 3분할 chi-square."""
    if stats is None:
        from app.scoring import ab_test
        stats = ab_test.get_stats()
    a = stats.get("a", {}) or {}
    b = stats.get("b", {}) or {}
    succ_a = int(a.get("block", 0))
    n_a = int(a.get("count", 0))
    succ_b = int(b.get("block", 0))
    n_b = int(b.get("count", 0))
    return {
        "block_rate_z_test": two_proportion_z_test(succ_a, n_a, succ_b, n_b),
        "action_chi_square": chi_square_3way(a, b),
        "samples": {"a": n_a, "b": n_b},
    }
