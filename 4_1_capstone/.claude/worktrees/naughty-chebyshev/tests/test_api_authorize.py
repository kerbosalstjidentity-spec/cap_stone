"""FastAPI /v1/authorize 엔드포인트 테스트.

실제 모델 번들을 로드하지 않고, 최소 인메모리 번들로 API 동작을 검증한다.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi 미설치", allow_module_level=True)


def _make_tiny_bundle(tmp_path: Path) -> Path:
    """테스트용 최소 RF 번들을 임시 파일로 저장."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    from schema import FDSSchema

    n = 60
    rng = np.random.default_rng(0)
    feat_names = [f"V{i}" for i in range(1, 31)]
    X = rng.standard_normal((n, 30))
    y = np.array([0] * 50 + [1] * 10)
    X[50:, 13] -= 5.0  # V14 이동 (사기)

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(n_estimators=5, random_state=0)),
    ])
    pipe.fit(X, y)

    schema_path = ROOT / "schemas" / "fds" / "schema_v1_open.yaml"
    schema = FDSSchema.from_yaml(schema_path)

    bundle: dict[str, Any] = {
        "pipeline": pipe,
        "schema_raw": schema.raw,
        "feature_names": feat_names,
        "clf_step_name": "clf",
        "eval_method": "test",
    }
    bundle_path = tmp_path / "test_bundle.joblib"
    joblib.dump(bundle, bundle_path)
    return bundle_path


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """임시 번들 파일로 API TestClient 생성."""
    tmp = tmp_path_factory.mktemp("bundle")
    bundle_path = _make_tiny_bundle(tmp)

    import os
    os.environ["FDS_BUNDLE_PATH"] = str(bundle_path)

    import importlib
    import api_score_app
    importlib.reload(api_score_app)

    with TestClient(api_score_app.app) as c:
        yield c


def _fraud_row() -> dict:
    """V14를 크게 이동시킨 고위험 거래."""
    row = {f"V{i}": 0.0 for i in range(1, 31)}
    row["V14"] = -8.0  # 사기 신호
    row["transaction_id"] = "TEST_FRAUD"
    return row


def _normal_row() -> dict:
    """정상적인 평균 거래."""
    return {f"V{i}": 0.0 for i in range(1, 31)}


class TestHealthEndpoint:
    def test_health_ok(self, client) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestScoreSingle:
    def test_returns_score(self, client) -> None:
        r = client.post("/v1/score/single", json=_normal_row())
        assert r.status_code == 200
        body = r.json()
        assert "score" in body
        assert 0.0 <= body["score"] <= 1.0

    def test_missing_feature_returns_400(self, client) -> None:
        r = client.post("/v1/score/single", json={"V1": 1.0})
        assert r.status_code == 400


class TestAuthorizeEndpoint:
    def test_normal_transaction_approved(self, client) -> None:
        r = client.post("/v1/authorize", json=_normal_row())
        assert r.status_code == 200
        body = r.json()
        assert "decision" in body
        assert body["decision"] in ("APPROVED", "PENDING", "DECLINED")
        assert "score" in body
        assert "transaction_id" in body
        assert "threshold_used" in body

    def test_fraud_transaction_declined(self, client) -> None:
        """V14 크게 이동 → 정상보다 높은 score 확인.

        테스트 번들은 5트리/60행으로 작아 절대값보다 상대적 순위를 검증한다.
        """
        normal = client.post("/v1/authorize", json=_normal_row()).json()
        fraud = client.post("/v1/authorize", json=_fraud_row()).json()
        assert fraud["score"] > normal["score"], (
            f"사기 스코어({fraud['score']:.3f}) ≤ 정상 스코어({normal['score']:.3f})"
        )

    def test_transaction_id_passthrough(self, client) -> None:
        row = _normal_row()
        row["transaction_id"] = "MY_TXN_123"
        r = client.post("/v1/authorize", json=row)
        assert r.json()["transaction_id"] == "MY_TXN_123"

    def test_reason_codes_present(self, client) -> None:
        r = client.post("/v1/authorize", json=_fraud_row())
        body = r.json()
        assert "reason_codes" in body

    def test_threshold_keys_present(self, client) -> None:
        r = client.post("/v1/authorize", json=_normal_row())
        th = r.json()["threshold_used"]
        assert "block_min" in th
        assert "review_min" in th

    def test_missing_feature_returns_400(self, client) -> None:
        r = client.post("/v1/authorize", json={"V1": 1.0})
        assert r.status_code == 400


class TestScoreBatch:
    def test_batch_two_rows(self, client) -> None:
        rows = [_normal_row(), _fraud_row()]
        r = client.post("/v1/score/batch", json=rows)
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        assert body[1]["score"] > body[0]["score"]

    def test_empty_batch_returns_400(self, client) -> None:
        r = client.post("/v1/score/batch", json=[])
        assert r.status_code == 400
