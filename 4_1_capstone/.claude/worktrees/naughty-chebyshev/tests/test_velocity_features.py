"""velocity_features.py 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

from velocity_features import compute_velocity_features  # noqa: E402


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestGracefulFallback:
    """필수 컬럼 없을 때 zero-fill 반환."""

    def test_no_required_columns(self) -> None:
        df = pd.DataFrame({"V1": [1.0, 2.0]})
        result = compute_velocity_features(df)
        assert "tx_count_1h" in result.columns
        assert result["tx_count_1h"].sum() == 0

    def test_missing_user_id(self) -> None:
        df = pd.DataFrame({
            "event_ts": ["2025-01-01T10:00:00", "2025-01-01T10:30:00"],
            "amount": [100.0, 200.0],
            "country_txn": ["KR", "KR"],
        })
        result = compute_velocity_features(df)
        assert result["tx_count_1h"].sum() == 0


class TestTxCount1h:
    """1시간 내 거래 건수 계산."""

    def test_single_transaction(self) -> None:
        df = _make_df([{
            "user_id": "U1", "event_ts": "2025-01-01T10:00:00",
            "amount": 100.0, "country_txn": "KR",
        }])
        result = compute_velocity_features(df)
        assert result.iloc[0]["tx_count_1h"] == 0  # 첫 거래 → 이전 없음

    def test_two_within_1h(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T10:30:00", "amount": 200.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        assert result.iloc[0]["tx_count_1h"] == 0
        assert result.iloc[1]["tx_count_1h"] == 1  # 30분 전 거래 1건

    def test_two_outside_1h(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T08:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 200.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        assert result.iloc[1]["tx_count_1h"] == 0  # 2시간 전 → 1h 범위 밖

    def test_different_users_isolated(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U2", "event_ts": "2025-01-01T10:30:00", "amount": 200.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        # U2의 거래가 U1의 1h 카운트에 포함되면 안 됨
        assert result.iloc[1]["tx_count_1h"] == 0


class TestAmountSum:
    """24시간 누적 금액 계산."""

    def test_amount_sum_24h(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T12:00:00", "amount": 200.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T14:00:00", "amount": 300.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        # 3번째 거래 기준 24h 내 이전 금액 합 = 100+200=300
        assert abs(result.iloc[2]["amount_sum_24h"] - 300.0) < 1e-6

    def test_amount_outside_24h_excluded(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T00:00:00", "amount": 999.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-02T01:00:00", "amount": 100.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        # 25시간 전 거래는 24h 합계에서 제외
        assert result.iloc[1]["amount_sum_24h"] == 0.0


class TestCountryChangeFlag:
    """국가 변경 플래그."""

    def test_no_change(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T11:00:00", "amount": 100.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        assert result.iloc[0]["country_change_flag"] == 0  # 첫 거래
        assert result.iloc[1]["country_change_flag"] == 0  # 동일 국가

    def test_country_changed(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 100.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T11:00:00", "amount": 100.0, "country_txn": "US"},
        ])
        result = compute_velocity_features(df)
        assert result.iloc[1]["country_change_flag"] == 1


class TestVelocityRatio:
    """tx_velocity_ratio = tx_count_1h / (tx_count_24h + 1)."""

    def test_ratio_formula(self) -> None:
        df = _make_df([
            {"user_id": "U1", "event_ts": "2025-01-01T09:30:00", "amount": 10.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T09:45:00", "amount": 10.0, "country_txn": "KR"},
            {"user_id": "U1", "event_ts": "2025-01-01T10:00:00", "amount": 10.0, "country_txn": "KR"},
        ])
        result = compute_velocity_features(df)
        row = result.iloc[2]
        expected = row["tx_count_1h"] / (row["tx_count_24h"] + 1)
        assert abs(row["tx_velocity_ratio"] - expected) < 1e-9

    def test_zero_ratio_for_first_tx(self) -> None:
        df = _make_df([{
            "user_id": "U1", "event_ts": "2025-01-01T10:00:00",
            "amount": 100.0, "country_txn": "KR",
        }])
        result = compute_velocity_features(df)
        # tx_count_1h=0, tx_count_24h=0 → ratio = 0/(0+1) = 0
        assert result.iloc[0]["tx_velocity_ratio"] == 0.0
