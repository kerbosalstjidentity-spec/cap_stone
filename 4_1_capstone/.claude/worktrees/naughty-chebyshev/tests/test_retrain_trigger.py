"""retrain_trigger.py 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

from retrain_trigger import _classify_features, _extract_psi_per_feature  # noqa: E402


class TestExtractPsiPerFeature:
    """drift JSON 포맷 A/B 모두 파싱 가능한지 검증."""

    def test_format_b_psi_per_feature_dict(self) -> None:
        data = {"psi_per_feature": {"V1": 0.03, "V14": 0.28, "V4": 0.12}}
        result = _extract_psi_per_feature(data)
        assert result["V1"] == pytest.approx(0.03)
        assert result["V14"] == pytest.approx(0.28)

    def test_format_a_per_column_array(self) -> None:
        data = {"per_column": [
            {"column": "V1", "psi": 0.05},
            {"column": "V14", "psi": 0.30},
        ]}
        result = _extract_psi_per_feature(data)
        assert result["V1"] == pytest.approx(0.05)
        assert result["V14"] == pytest.approx(0.30)

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="PSI 데이터를 찾을 수 없습니다"):
            _extract_psi_per_feature({"unknown_key": {}})


class TestClassifyFeatures:
    """PSI 심각도 분류 (critical > 0.25, major > 0.10)."""

    def test_all_negligible(self) -> None:
        psi = {"V1": 0.01, "V2": 0.05, "V3": 0.08}
        major, critical = _classify_features(psi)
        assert major == []
        assert critical == []

    def test_major_only(self) -> None:
        psi = {"V1": 0.15, "V2": 0.20, "V3": 0.05}
        major, critical = _classify_features(psi)
        assert set(major) == {"V1", "V2"}
        assert critical == []

    def test_critical_only(self) -> None:
        psi = {"V14": 0.30, "V1": 0.05}
        major, critical = _classify_features(psi)
        assert "V14" in critical
        assert "V14" not in major  # critical은 major에 포함되지 않음

    def test_mixed(self) -> None:
        psi = {"V1": 0.12, "V2": 0.28, "V3": 0.07}
        major, critical = _classify_features(psi)
        assert "V1" in major
        assert "V2" in critical
        assert "V3" not in major and "V3" not in critical

    def test_trigger_condition_critical_1(self) -> None:
        """critical 1개 → 트리거 조건 충족."""
        psi = {"V14": 0.30}
        major, critical = _classify_features(psi)
        should_trigger = len(critical) >= 1 or len(major) >= 3
        assert should_trigger is True

    def test_trigger_condition_major_3(self) -> None:
        """major 3개 이상 → 트리거 조건 충족."""
        psi = {"V1": 0.12, "V2": 0.15, "V3": 0.18}
        major, critical = _classify_features(psi)
        should_trigger = len(critical) >= 1 or len(major) >= 3
        assert should_trigger is True

    def test_no_trigger_major_2(self) -> None:
        """major 2개, critical 0개 → 트리거 안됨."""
        psi = {"V1": 0.12, "V2": 0.15, "V3": 0.05}
        major, critical = _classify_features(psi)
        should_trigger = len(critical) >= 1 or len(major) >= 3
        assert should_trigger is False

    def test_boundary_exactly_0_25(self) -> None:
        """PSI = 0.25 → major (critical은 strict > 0.25)."""
        psi = {"V1": 0.25}
        major, critical = _classify_features(psi)
        assert "V1" in major
        assert "V1" not in critical

    def test_boundary_just_above_0_25(self) -> None:
        """PSI = 0.2501 → critical."""
        psi = {"V1": 0.2501}
        major, critical = _classify_features(psi)
        assert "V1" in critical
