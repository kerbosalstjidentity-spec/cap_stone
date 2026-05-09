"""W5-#5: reason_codes 에 학습 시 mu/std 주입 — 단건 z-score 일관성."""
from __future__ import annotations

import numpy as np

from app.scoring.reason_codes import (
    reason_code_to_human,
    single_reason,
    top_feature_reasons,
)


def test_single_reason_with_external_mu_std_changes_top():
    names = ["a", "b", "c"]
    importances = np.array([0.3, 0.3, 0.4])  # c 가 약간 큼
    x = np.array([10.0, 1.0, 0.5])
    # 학습 mu/std: a 가 매우 큼 (mu=0, std=1) → z_a 폭발
    mu = np.array([0.0, 0.0, 0.5])
    std = np.array([1.0, 1.0, 1.0])
    rc_with = single_reason(x, names, importances, mu=mu, std=std)
    # mu/std 미주입 시 단건 분산=0 → 순수 importance 순서 (c 가 1위)
    rc_without = single_reason(x, names, importances)
    assert rc_with.split(";")[0] == "a"
    assert rc_without.split(";")[0] == "c"


def test_top_feature_reasons_fallback_without_mu_std():
    X = np.array([[1.0, 2.0], [2.0, 4.0]])
    out = top_feature_reasons(X, ["x", "y"], np.array([0.5, 0.5]))
    assert len(out) == 2


def test_human_uses_external_std_for_sigma():
    names = ["a"]
    importances = np.array([1.0])
    x = np.array([5.0])
    mu = np.array([0.0])
    std = np.array([1.0])  # z = 5σ → "극단값" 메시지
    descs = reason_code_to_human(x, names, importances, mu=mu, std=std)
    assert "극단값" in descs[0] or "벗어났습니다" in descs[0]


def test_zero_std_clipped_to_min():
    names = ["a"]
    importances = np.array([1.0])
    x = np.array([1.0])
    mu = np.array([1.0])
    std = np.array([0.0])  # 클립되어 nan/inf 가 안 나야 함
    rc = single_reason(x, names, importances, mu=mu, std=std)
    assert rc == "a"
