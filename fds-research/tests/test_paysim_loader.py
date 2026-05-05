"""W5.5-#2 — PaySim 로더 스모크 테스트.

CSV 가 존재할 때만 실제 로드 검증. 없으면 skip.
"""
from __future__ import annotations

import pytest

from scripts.paysim.load import REQUIRED_COLUMNS, load_paysim, resolve_path, summary


@pytest.fixture(scope="module")
def csv_path():
    p = resolve_path()
    if not p.exists():
        pytest.skip(f"PaySim CSV not present at {p}; run `make paysim-download`")
    return p


def test_loader_columns_and_dtypes(csv_path):
    df = load_paysim(sample=5_000)
    for col in REQUIRED_COLUMNS:
        assert col in df.columns, f"missing column {col}"
    assert df["isFraud"].isin([0, 1]).all()
    assert (df["amount"] >= 0).all()


def test_loader_type_filter(csv_path):
    df = load_paysim(types=("TRANSFER", "CASH_OUT"), sample=10_000)
    assert set(df["type"].unique()) <= {"TRANSFER", "CASH_OUT"}
    # 사기는 TRANSFER + CASH_OUT 에만 존재 → 필터해도 사기 보존
    assert df["isFraud"].sum() > 0


def test_summary_structure(csv_path):
    df = load_paysim(sample=2_000)
    s = summary(df)
    assert {"rows", "fraud_rows", "fraud_rate", "type_counts", "amount", "step_range"} <= s.keys()
    assert s["rows"] == len(df)
