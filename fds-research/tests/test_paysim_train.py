"""W5.5-#3 — train_paysim 산출물 검증 (스모크).

번들 파일이 존재할 때만 로드·예측 호환성을 검증. 학습 자체는 본 테스트
범위 밖(시간이 큰 RF/IF fit) — `python train_paysim.py --max-rows 100000`
로 사전에 산출해 두는 것을 가정.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = REPO_ROOT / "outputs" / "fds" / "model_bundle_paysim.joblib"


@pytest.fixture(scope="module")
def bundle():
    if not BUNDLE_PATH.exists():
        pytest.skip(
            f"PaySim bundle absent at {BUNDLE_PATH}. "
            "Run `python train_paysim.py --max-rows 200000` first."
        )
    return joblib.load(BUNDLE_PATH)


def test_bundle_keys(bundle):
    expected = {
        "domain",
        "if_model",
        "rf_model",
        "feature_names",
        "raw_feature_names",
        "type_categories",
        "trained_at",
        "metrics",
        "block_min",
        "review_min",
    }
    assert expected <= bundle.keys()
    assert bundle["domain"] == "paysim"
    assert bundle["type_categories"] == ["TRANSFER", "CASH_OUT"]


def test_bundle_predict_shape(bundle):
    n_features = len(bundle["feature_names"])
    X = np.zeros((3, n_features), dtype=np.float32)
    proba = bundle["rf_model"].predict_proba(X)
    assert proba.shape == (3, 2)
    assert (0.0 <= proba).all() and (proba <= 1.0).all()


def test_bundle_metrics_quality(bundle):
    m = bundle["metrics"]
    # 본격 학습(--max-rows 미지정) 결과 PR-AUC ≥0.9 기대.
    # 스모크(100K 행) 산출물도 동일 기준 충족함을 확인했음.
    assert m["roc_auc"] >= 0.9
    assert m["pr_auc"] >= 0.9
    assert m["recall_in_queue"] >= 0.9
