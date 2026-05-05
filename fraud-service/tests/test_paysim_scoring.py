"""W5.5-#4 — fraud-service 의 PaySim 번들 스코어링 wiring 테스트.

번들 파일은 fds-research 산출물(``model_bundle_paysim.joblib``)을 ``MODEL_PATH``
환경변수로 가리켜 사용한다. 부재 시 skip.
"""
from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.scoring.ensemble import (
    ANOMALY_RANGES,
    _normalize_anomaly,
    score_paysim_bundle,
)
from app.scoring.features import (
    build_paysim_row,
    paysim_dict_to_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYSIM_BUNDLE = REPO_ROOT / "fds-research" / "outputs" / "fds" / "model_bundle_paysim.joblib"


def test_build_paysim_row_keys():
    row = build_paysim_row({
        "type": "TRANSFER",
        "amount": 1000,
        "oldbalanceOrg": 5000,
        "newbalanceOrig": 4000,
        "oldbalanceDest": 0,
        "newbalanceDest": 1000,
        "nameDest": "C123",
        "step": 5,
    })
    assert row["amount"] == 1000.0
    # errorBalanceOrig = 5000 - 1000 - 4000 = 0
    assert row["errorBalanceOrig"] == 0.0
    # errorBalanceDest = 0 + 1000 - 1000 = 0
    assert row["errorBalanceDest"] == 0.0
    assert row["type_TRANSFER"] == 1.0
    assert row["type_CASH_OUT"] == 0.0
    assert row["is_dest_merchant"] == 0.0


def test_build_paysim_row_merchant_dest():
    row = build_paysim_row({"type": "PAYMENT", "amount": 100, "nameDest": "M999"})
    assert row["is_dest_merchant"] == 1.0
    assert row["type_TRANSFER"] == row["type_CASH_OUT"] == 0.0


def test_normalize_anomaly_paysim_range():
    low, high = ANOMALY_RANGES["paysim"]
    # 풀 데이터 측정 기반 (-0.69, -0.36) — fraud p10 / normal p90
    assert low == -0.69 and high == -0.36
    assert _normalize_anomaly(high, domain="paysim") == 0.0  # 정상 끝
    assert _normalize_anomaly(low, domain="paysim") == 1.0   # 이상 끝
    assert 0.0 < _normalize_anomaly((low + high) / 2, domain="paysim") < 1.0


def test_normalize_anomaly_open_unchanged():
    # 레거시 open 도메인 정규화 호환성 — 기존 동작 유지
    assert _normalize_anomaly(-0.05, domain="open") == 0.0
    assert _normalize_anomaly(-0.5, domain="open") == 1.0


@pytest.fixture(scope="module")
def paysim_bundle():
    if not PAYSIM_BUNDLE.exists():
        pytest.skip(f"PaySim bundle absent at {PAYSIM_BUNDLE}")
    return joblib.load(PAYSIM_BUNDLE)


def test_score_paysim_bundle_fraud_pattern(paysim_bundle):
    # 잔액 모순 + 큰 금액 — 사기 의심 강한 패턴
    payload = {
        "type": "TRANSFER",
        "amount": 200_000,
        "oldbalanceOrg": 200_000,
        "newbalanceOrig": 0,
        "oldbalanceDest": 0,
        "newbalanceDest": 0,  # 잔액 미반영
        "nameDest": "C999",
        "step": 100,
    }
    raw_names = paysim_bundle["raw_feature_names"]
    X = paysim_dict_to_matrix(payload, raw_names)
    out = score_paysim_bundle(paysim_bundle, X)
    assert 0.0 <= out["fraud_probability"] <= 1.0
    assert out["anomaly_score"] < 0  # IF score_samples 는 음수
    assert 0.0 <= out["anomaly_normalized"] <= 1.0


def test_score_paysim_bundle_normal_pattern(paysim_bundle):
    # 정상 결제 — merchant dest, balance 변화 일치
    payload = {
        "type": "PAYMENT",
        "amount": 50.0,
        "oldbalanceOrg": 1000.0,
        "newbalanceOrig": 950.0,
        "oldbalanceDest": 0,
        "newbalanceDest": 0,
        "nameDest": "M1234",
        "step": 50,
    }
    raw_names = paysim_bundle["raw_feature_names"]
    X = paysim_dict_to_matrix(payload, raw_names)
    out = score_paysim_bundle(paysim_bundle, X)
    assert out["fraud_probability"] < 0.5


def test_route_score_paysim(paysim_bundle, monkeypatch):
    """`/v1/score` 가 ``domain=paysim`` 번들에서 동작하는지 검증."""
    monkeypatch.setenv("MODEL_PATH", str(PAYSIM_BUNDLE))
    # settings 는 import 시 캐시되므로 fresh 인스턴스로 patch
    from app import config as cfg
    monkeypatch.setattr(cfg.settings, "model_path", str(PAYSIM_BUNDLE))

    from app.main import app
    client = TestClient(app)

    payload = {
        "features": {
            "type": "TRANSFER",
            "amount": 200_000,
            "oldbalanceOrg": 200_000,
            "newbalanceOrig": 0,
            "oldbalanceDest": 0,
            "newbalanceDest": 0,
            "nameDest": "C999",
            "step": 100,
        }
    }
    r = client.post("/v1/score", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("domain") == "paysim"
    assert data.get("fraud_probability") is not None
    assert "anomaly_score" in data
