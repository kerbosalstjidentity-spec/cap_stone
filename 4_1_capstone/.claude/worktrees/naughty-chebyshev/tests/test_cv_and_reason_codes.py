"""train_export_rf CV 로직, reason_codes, ops_drift PSI 심각도 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

from reason_codes import top_feature_reasons  # noqa: E402
from ops_drift import _psi_severity  # noqa: E402


# ── reason_codes ──────────────────────────────────────────────────────────────

def test_top_feature_reasons_shape() -> None:
    """행마다 top_k개 특성 이름을 반환해야 한다."""
    X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    names = ["V1", "V2", "V3"]
    importances = np.array([0.5, 0.3, 0.2])
    result = top_feature_reasons(X, names, importances, top_k=2)
    assert len(result) == 2
    for r in result:
        parts = r.split(";")
        assert len(parts) == 2
        assert all(p in names for p in parts)


def test_top_feature_reasons_top1() -> None:
    """top_k=1이면 세미콜론 없이 특성 하나만 반환해야 한다."""
    X = np.array([[10.0, 0.0, 0.0]])
    names = ["A", "B", "C"]
    importances = np.array([1.0, 0.0, 0.0])
    result = top_feature_reasons(X, names, importances, top_k=1)
    assert result[0] == "A"


def test_top_feature_reasons_high_importance_wins() -> None:
    """중요도가 높은 특성이 편차가 낮아도 낮은 중요도 특성을 이겨야 한다."""
    X = np.array([[0.0, 100.0]])   # V2가 배치 내 편차 압도적
    names = ["V1", "V2"]
    importances = np.array([0.99, 0.01])  # 하지만 V1 중요도 압도적
    result = top_feature_reasons(X, names, importances, top_k=1)
    # V1: 0.99 * (1 + ~0) vs V2: 0.01 * (1 + z_V2)
    # z_V2 = |100 - 100| / eps = 0  (배치 1행이면 std=0)
    # 즉 둘 다 z≈0이므로 중요도 높은 V1이 1위
    assert result[0] == "V1"


def test_top_feature_reasons_single_row() -> None:
    """행이 1개여도 오류 없이 동작해야 한다."""
    X = np.array([[5.0, -3.0, 1.0]])
    names = ["V1", "V2", "V3"]
    importances = np.array([0.4, 0.4, 0.2])
    result = top_feature_reasons(X, names, importances, top_k=3)
    assert len(result) == 1
    assert len(result[0].split(";")) == 3


# ── CV 인자 검증 ──────────────────────────────────────────────────────────────

def test_cv_folds_requires_enough_fraud() -> None:
    """사기 건수 < fold 수면 ValueError를 내야 한다."""
    import pandas as pd
    from unittest.mock import patch, MagicMock

    # argparse 시뮬레이션 대신 run_cv 직접 호출
    from train_export_rf import run_cv

    np.random.seed(42)
    n = 100
    X = pd.DataFrame({"V1": np.random.randn(n), "V2": np.random.randn(n)})
    # 사기 3건, fold=5 → 에러 예상
    y = pd.Series([1, 1, 1] + [0] * (n - 3))

    with pytest.raises(Exception):
        # 사기 3 < fold 5 이므로 StratifiedKFold 자체가 실패해야 함
        run_cv(X, y, n_splits=5, imputer_strategy="median",
               block_min=0.5, review_min=0.35)


def test_cv_produces_per_fold_metrics() -> None:
    """CV 실행 시 fold별 AUC 리스트가 반환되어야 한다."""
    import pandas as pd
    from train_export_rf import run_cv

    np.random.seed(0)
    n = 200
    # 사기 20건, fold=4 → fold당 5건
    fraud_idx = np.random.choice(n, 20, replace=False)
    y_arr = np.zeros(n, dtype=int)
    y_arr[fraud_idx] = 1
    X = pd.DataFrame({"V1": np.random.randn(n), "V2": np.random.randn(n)})
    y = pd.Series(y_arr)

    metrics, pipe = run_cv(X, y, n_splits=4, imputer_strategy="median",
                           block_min=0.5, review_min=0.35)

    assert metrics["eval_method"] == "stratified_kfold_cv"
    assert len(metrics["roc_auc_per_fold"]) == 4
    assert len(metrics["pr_auc_per_fold"]) == 4
    assert metrics["roc_auc_mean"] is not None
    assert 0.0 <= metrics["roc_auc_mean"] <= 1.0
    assert pipe is not None


# ── PSI 심각도 등급 ────────────────────────────────────────────────────────────

def test_psi_severity_boundaries() -> None:
    """PSI 값이 각 등급 경계를 올바르게 분류해야 한다."""
    assert _psi_severity(0.0) == "negligible"
    assert _psi_severity(0.09) == "negligible"
    assert _psi_severity(0.10) == "minor"
    assert _psi_severity(0.24) == "minor"
    assert _psi_severity(0.25) == "moderate"
    assert _psi_severity(0.49) == "moderate"
    assert _psi_severity(0.50) == "major"
    assert _psi_severity(0.99) == "major"
    assert _psi_severity(1.00) == "critical"
    assert _psi_severity(1.445) == "critical"   # V30 실제 관측값


def test_psi_severity_v30_is_critical() -> None:
    """V30의 실측 PSI=1.445는 반드시 critical 등급이어야 한다."""
    assert _psi_severity(1.4452168927370466) == "critical"


# ── PSI 계산 함수 단위 테스트 ────────────────────────────────────────────────

from ops_drift import _psi  # noqa: E402


def test_psi_identical_distributions_near_zero() -> None:
    """동일 분포 → PSI ≈ 0 (< 0.01)."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(500)
    result = _psi(x, x.copy())
    assert result < 0.01, f"동일 분포인데 PSI={result:.4f}"


def test_psi_completely_different_distributions_large() -> None:
    """완전히 다른 분포 (정규(0,1) vs 정규(10,1)) → PSI > 1.0."""
    rng = np.random.default_rng(1)
    ref = rng.standard_normal(500)
    cur = rng.standard_normal(500) + 10.0   # 평균 10 이동
    result = _psi(ref, cur)
    assert result > 1.0, f"완전히 다른 분포인데 PSI={result:.4f}"


def test_psi_moderate_shift_in_expected_range() -> None:
    """중간 이동 (정규(0,1) vs 정규(0.5,1)) → PSI 0.01–0.50 범위 내 (minor~moderate)."""
    rng = np.random.default_rng(2)
    ref = rng.standard_normal(500)
    cur = rng.standard_normal(500) + 0.5   # 0.5σ 이동 — minor 범위 예상
    result = _psi(ref, cur)
    assert 0.01 <= result <= 0.50, f"중간 이동 PSI={result:.4f} 범위 벗어남"


def test_psi_too_few_samples_returns_nan() -> None:
    """샘플이 buckets*2 미만이면 nan을 반환해야 한다."""
    ref = np.array([1.0, 2.0, 3.0])   # 3개 < 10*2=20
    cur = np.array([1.0, 2.0, 3.0])
    result = _psi(ref, cur, buckets=10)
    assert np.isnan(result), f"샘플 부족인데 nan이 아님: {result}"


def test_psi_with_nan_values_ignored() -> None:
    """입력에 nan이 포함돼도 제거 후 계산 — 오류 없이 유한값 반환."""
    rng = np.random.default_rng(3)
    ref = rng.standard_normal(500)
    cur = rng.standard_normal(500)
    # 일부를 nan으로 교체
    ref_with_nan = ref.copy()
    ref_with_nan[::5] = np.nan
    result = _psi(ref_with_nan, cur)
    assert np.isfinite(result), f"nan 포함 입력인데 유한값 아님: {result}"


def test_psi_nonnegative() -> None:
    """PSI는 항상 0 이상이어야 한다 (수학적 속성)."""
    rng = np.random.default_rng(4)
    for _ in range(5):
        ref = rng.standard_normal(300)
        cur = rng.standard_normal(300) * rng.uniform(0.5, 2.0)
        result = _psi(ref, cur)
        if not np.isnan(result):
            assert result >= 0.0, f"PSI 음수 발생: {result:.6f}"
