"""End-to-End 파이프라인 통합 테스트.

실제 CSV 없이 인메모리 mock 번들로 전체 흐름을 검증:
  schema.prepare_frame
    → scoring.score_prepared_frame
    → rules_engine.evaluate_rules (YAML 경유)
    → policy_merge.merge_actions / decide_from_score

검증 항목:
  - 출력 컬럼 존재 여부 (transaction_id, score, reason_code, final_action, audit_summary)
  - score 범위 [0, 1]
  - final_action 이 PASS / REVIEW / BLOCK 중 하나
  - audit_summary 비어 있지 않음 (모델 reason_code 또는 rule_ids가 있을 때)
  - YAML 스키마 검증: 빈 features, version 누락 시 ValueError
  - YAML 규칙 검증: id/action 누락 규칙에 경고만 발생 (중단 없음)
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FDS = ROOT / "scripts" / "fds"
sys.path.insert(0, str(FDS))

from schema import FDSSchema                          # noqa: E402
from scoring import score_prepared_frame              # noqa: E402
from rules_engine import evaluate_rules, _validate_rules_cfg  # noqa: E402
from policy_merge import merge_actions, decide_from_score, audit_summary  # noqa: E402


# ── 인메모리 mock 번들 생성 ───────────────────────────────────────────────────

FEATURE_NAMES = ["F1", "F2", "F3", "F4", "F5"]
N_FEATURES = len(FEATURE_NAMES)


def _make_mock_bundle() -> dict[str, Any]:
    """소형 RandomForest 파이프라인을 인메모리 학습 → 번들 딕셔너리 반환."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    rng = np.random.default_rng(42)
    n = 200
    X_tr = rng.standard_normal((n, N_FEATURES))
    y_tr = (rng.random(n) < 0.1).astype(int)   # ~10 % 사기

    imputer = SimpleImputer(strategy="median")
    clf = RandomForestClassifier(n_estimators=10, random_state=0)
    pipe = Pipeline([("imputer", imputer), ("clf", clf)])
    pipe.fit(X_tr, y_tr)

    schema_raw: dict[str, Any] = {
        "version": "1",
        "name": "mock_e2e",
        "id": {"canonical": "transaction_id", "synthetic_from_index": True},
        "features": FEATURE_NAMES,
        "label": {"canonical": "is_fraud"},
        "missing": {"imputer_strategy": "median"},
    }

    return {
        "schema_raw": schema_raw,
        "pipeline": pipe,
        "feature_names": FEATURE_NAMES,
    }


BUNDLE = _make_mock_bundle()


# ── mock 데이터프레임 ──────────────────────────────────────────────────────────

def _make_df(n: int = 20, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {f: rng.standard_normal(n) for f in FEATURE_NAMES}
    data["is_fraud"] = (rng.random(n) < 0.1).astype(int)
    return pd.DataFrame(data)


# ── mock rules YAML 픽스처 ────────────────────────────────────────────────────

@pytest.fixture()
def rules_yaml_path(tmp_path: Path) -> Path:
    """최소 규칙 YAML: F1 > 2.0이면 REVIEW."""
    rules = {
        "rules": [
            {"id": "R001", "action": "REVIEW", "amount_above": 2.0},
        ]
    }
    p = tmp_path / "rules.yaml"
    p.write_text(yaml.dump(rules), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  테스트: 스코어링 파이프라인
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringPipeline:
    """schema → scoring 단계 통합 검증."""

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        schema = FDSSchema.from_dict(BUNDLE["schema_raw"])
        return schema.prepare_frame(df)

    def test_output_columns_present(self) -> None:
        df = _make_df()
        prepared = self._prepare(df)
        result = score_prepared_frame(prepared, BUNDLE)
        assert set(result.columns) >= {"transaction_id", "score", "reason_code", "reason_method"}

    def test_score_in_unit_interval(self) -> None:
        df = _make_df(n=50)
        prepared = self._prepare(df)
        result = score_prepared_frame(prepared, BUNDLE)
        assert result["score"].between(0.0, 1.0).all(), "score 가 [0,1] 범위를 벗어남"

    def test_row_count_matches(self) -> None:
        n = 15
        df = _make_df(n=n)
        prepared = self._prepare(df)
        result = score_prepared_frame(prepared, BUNDLE)
        assert len(result) == n

    def test_reason_code_top3_format(self) -> None:
        df = _make_df(n=10)
        prepared = self._prepare(df)
        result = score_prepared_frame(prepared, BUNDLE, top_reasons=3)
        for rc in result["reason_code"]:
            parts = rc.split(";")
            assert 1 <= len(parts) <= 3, f"reason_code 형식 오류: {rc!r}"
            assert all(p in FEATURE_NAMES for p in parts), f"알 수 없는 특성명: {rc!r}"

    def test_transaction_id_unique(self) -> None:
        df = _make_df(n=20)
        prepared = self._prepare(df)
        result = score_prepared_frame(prepared, BUNDLE)
        assert result["transaction_id"].nunique() == len(result), "transaction_id 중복"


# ─────────────────────────────────────────────────────────────────────────────
#  테스트: policy_merge
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyMerge:
    """decide_from_score / merge_actions / audit_summary 단위 검증."""

    @pytest.mark.parametrize("score,expected", [
        (0.9, "BLOCK"),
        (0.4, "REVIEW"),
        (0.1, "PASS"),
    ])
    def test_decide_from_score(self, score: float, expected: str) -> None:
        action = decide_from_score(score, block_min=0.7, review_min=0.3)
        assert action == expected

    def test_merge_higher_wins(self) -> None:
        assert merge_actions("PASS", "BLOCK") == "BLOCK"
        assert merge_actions("REVIEW", "PASS") == "REVIEW"
        assert merge_actions("BLOCK", "REVIEW") == "BLOCK"

    def test_audit_summary_both(self) -> None:
        s = audit_summary("V1;V3", "R001;R002")
        assert "model:" in s
        assert "rules:" in s

    def test_audit_summary_empty(self) -> None:
        assert audit_summary("", "") == ""


# ─────────────────────────────────────────────────────────────────────────────
#  테스트: YAML 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestYamlValidation:
    """스키마 YAML 및 규칙 YAML 검증 로직."""

    # ── schema.py ──

    def test_schema_missing_version_raises(self) -> None:
        with pytest.raises(ValueError, match="version"):
            FDSSchema.validate_schema_raw({"features": ["V1"]})

    def test_schema_missing_features_raises(self) -> None:
        with pytest.raises(ValueError, match="features"):
            FDSSchema.validate_schema_raw({"version": "1"})

    def test_schema_empty_features_raises(self) -> None:
        with pytest.raises(ValueError, match="비어 있습니다"):
            FDSSchema.validate_schema_raw({"version": "1", "features": []})

    def test_schema_features_not_list_raises(self) -> None:
        with pytest.raises(ValueError, match="리스트여야"):
            FDSSchema.validate_schema_raw({"version": "1", "features": "V1,V2"})

    def test_schema_valid_passes(self) -> None:
        FDSSchema.validate_schema_raw({"version": "1", "features": ["V1", "V2"]})

    def test_from_dict_propagates_validation(self) -> None:
        with pytest.raises(ValueError):
            FDSSchema.from_dict({"version": "1", "features": []})

    # ── rules_engine.py ──

    def test_rules_missing_id_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        cfg = {"rules": [{"action": "BLOCK", "amount_above": 999}]}
        with caplog.at_level(logging.WARNING, logger="rules_engine"):
            _validate_rules_cfg(cfg, source="test")
        assert "id" in caplog.text.lower()

    def test_rules_invalid_action_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        cfg = {"rules": [{"id": "R1", "action": "DENY", "amount_above": 999}]}
        with caplog.at_level(logging.WARNING, logger="rules_engine"):
            _validate_rules_cfg(cfg, source="test")
        assert "DENY" in caplog.text or "action" in caplog.text.lower()

    def test_rules_valid_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        cfg = {"rules": [{"id": "R1", "action": "REVIEW", "amount_above": 100}]}
        with caplog.at_level(logging.WARNING, logger="rules_engine"):
            _validate_rules_cfg(cfg, source="test")
        assert caplog.text == ""


# ─────────────────────────────────────────────────────────────────────────────
#  테스트: Full E2E (schema → score → rules → merge)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullE2E:
    """전체 파이프라인을 한 번에 실행하는 통합 시나리오."""

    def test_full_pipeline_produces_valid_decisions(
        self, rules_yaml_path: Path
    ) -> None:
        """20건 입력 → final_action 이 모두 PASS/REVIEW/BLOCK 이어야 한다."""
        df = _make_df(n=20)

        # 1) schema → prepared
        schema = FDSSchema.from_dict(BUNDLE["schema_raw"])
        prepared = schema.prepare_frame(df)

        # 2) scoring
        scores_df = score_prepared_frame(prepared, BUNDLE)

        # 3) rules
        rules_df = evaluate_rules(prepared, rules_yaml_path, rules_yaml_path.parent)

        # 4) policy merge
        valid_actions = {"PASS", "REVIEW", "BLOCK"}
        results = []
        for _, srow in scores_df.iterrows():
            tid = srow["transaction_id"]
            score = srow["score"]
            rc = srow["reason_code"]

            # rules lookup by position (index aligned)
            idx = scores_df.index[scores_df["transaction_id"] == tid][0]
            rule_row = rules_df.loc[idx]

            model_action = decide_from_score(score, block_min=0.7, review_min=0.3)
            final = merge_actions(rule_row["rule_action"], model_action)
            audit = audit_summary(rc, rule_row["rule_ids"])

            results.append({
                "transaction_id": tid,
                "score": score,
                "model_action": model_action,
                "rule_action": rule_row["rule_action"],
                "final_action": final,
                "audit_summary": audit,
            })

        out = pd.DataFrame(results)

        assert len(out) == 20
        assert out["final_action"].isin(valid_actions).all(), (
            f"유효하지 않은 final_action 발견: {out['final_action'].unique()}"
        )
        assert out["score"].between(0.0, 1.0).all()

    def test_pipeline_rejects_schema_mismatch(self) -> None:
        """특성 컬럼 누락 시 prepare_frame이 ValueError를 올려야 한다."""
        schema = FDSSchema.from_dict(BUNDLE["schema_raw"])
        bad_df = pd.DataFrame({"F1": [1.0], "F2": [2.0]})  # F3~F5 누락
        with pytest.raises(ValueError, match="스키마 특성 누락"):
            schema.prepare_frame(bad_df)
