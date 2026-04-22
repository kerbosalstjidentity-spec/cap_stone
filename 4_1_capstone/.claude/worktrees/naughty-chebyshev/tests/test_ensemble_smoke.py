"""train_export_ensemble.py + scoring.py 앙상블 번들 스모크 테스트."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402


def _tiny_ensemble_bundle(n_normal: int = 100, n_fraud: int = 10) -> dict:
    """최소 데이터로 RF+LGBM 앙상블 번들을 인메모리 생성."""
    try:
        from lightgbm import LGBMClassifier
    except ImportError:
        pytest.skip("lightgbm 미설치 — 앙상블 테스트 건너뜀")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    rng = np.random.default_rng(0)
    n = n_normal + n_fraud
    feat_names = [f"V{i}" for i in range(1, 31)]

    X = rng.standard_normal((n, 30))
    # fraud rows: V14 크게 이동
    X[n_normal:, 13] -= 5.0
    y = np.array([0] * n_normal + [1] * n_fraud)

    def make_pipe(clf):
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("clf", clf)])

    rf = make_pipe(RandomForestClassifier(n_estimators=10, random_state=0))
    lgbm = make_pipe(LGBMClassifier(n_estimators=10, random_state=0, verbosity=-1))
    rf.fit(X, y)
    lgbm.fit(pd.DataFrame(X, columns=feat_names), y)

    # schema_raw: schema_v1_open.yaml 내용 직접 구성
    schema_yaml_path = ROOT / "schemas" / "fds" / "schema_v1_open.yaml"
    schema = FDSSchema.from_yaml(schema_yaml_path)

    return {
        "ensemble": True,
        "models": [
            {"name": "rf", "pipeline": rf},
            {"name": "lgbm", "pipeline": lgbm},
        ],
        "ensemble_method": "avg",
        "schema_raw": schema.raw,
        "feature_names": feat_names,
    }


class TestEnsembleBundleStructure:
    """앙상블 번들 키 구조 검증."""

    def test_bundle_keys(self) -> None:
        bundle = _tiny_ensemble_bundle()
        assert bundle["ensemble"] is True
        assert len(bundle["models"]) == 2
        names = [m["name"] for m in bundle["models"]]
        assert "rf" in names
        assert "lgbm" in names

    def test_feature_names_count(self) -> None:
        bundle = _tiny_ensemble_bundle()
        assert len(bundle["feature_names"]) == 30


class TestScoringWithEnsemble:
    """score_prepared_frame이 앙상블 번들을 올바르게 처리하는지."""

    def test_returns_dataframe(self) -> None:
        bundle = _tiny_ensemble_bundle()
        schema = FDSSchema.from_dict(bundle["schema_raw"])

        rng = np.random.default_rng(1)
        feat_names = bundle["feature_names"]
        rows = {f: rng.standard_normal(5) for f in feat_names}
        rows["ID"] = [f"T{i}" for i in range(5)]
        df = pd.DataFrame(rows)
        df_prep = schema.prepare_frame(df)

        result = score_prepared_frame(df_prep, bundle)
        assert list(result.columns) == ["transaction_id", "score", "reason_code", "reason_method"]
        assert len(result) == 5

    def test_score_range(self) -> None:
        bundle = _tiny_ensemble_bundle()
        schema = FDSSchema.from_dict(bundle["schema_raw"])

        feat_names = bundle["feature_names"]
        rows = {f: np.random.standard_normal(10) for f in feat_names}
        rows["ID"] = [f"T{i}" for i in range(10)]
        df = schema.prepare_frame(pd.DataFrame(rows))

        result = score_prepared_frame(df, bundle)
        assert result["score"].between(0.0, 1.0).all()

    def test_fraud_higher_score_than_normal(self) -> None:
        """V14 크게 이동한 사기 거래가 정상보다 높은 스코어를 가져야 함."""
        bundle = _tiny_ensemble_bundle()
        schema = FDSSchema.from_dict(bundle["schema_raw"])
        feat_names = bundle["feature_names"]

        rng = np.random.default_rng(42)
        n = 20

        # 정상 거래
        normal_rows = {f: rng.standard_normal(n) for f in feat_names}
        normal_rows["ID"] = [f"N{i}" for i in range(n)]
        df_normal = schema.prepare_frame(pd.DataFrame(normal_rows))

        # 사기 거래 (V14 크게 이동)
        fraud_rows = {f: rng.standard_normal(n) for f in feat_names}
        fraud_rows["V14"] = rng.standard_normal(n) - 5.0
        fraud_rows["ID"] = [f"F{i}" for i in range(n)]
        df_fraud = schema.prepare_frame(pd.DataFrame(fraud_rows))

        normal_scores = score_prepared_frame(df_normal, bundle)["score"].mean()
        fraud_scores = score_prepared_frame(df_fraud, bundle)["score"].mean()

        assert fraud_scores > normal_scores, (
            f"사기 평균 스코어({fraud_scores:.3f})가 정상({normal_scores:.3f})보다 낮음"
        )
