"""W6-#1 — train_all 결과 joblib 영속화 + 부팅 자동 로드 테스트."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from app.ml.anomaly import anomaly_detector
from app.ml.classifier import overspend_classifier
from app.ml.clustering import cluster_model


def test_dump_and_load_roundtrip(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("ML_BUNDLE_DIR", td)
        # ml.persistence._bundle_dir 캐시 X — env 즉시 반영
        from app.ml.persistence import (
            bundle_paths,
            dump_all_models,
            load_all_models,
        )

        # 최소 학습: 카테고리 7개 균등 비율
        profiles = [
            {"food": 0.3, "shop": 0.4, "transport": 0.3},
            {"food": 0.5, "shop": 0.2, "transport": 0.3},
            {"food": 0.2, "shop": 0.5, "transport": 0.3},
        ]
        cluster_model.fit(profiles)

        anomaly_detector.fit([
            {"amount": 10000, "hour": 12, "is_domestic": True, "category_idx": 0},
            {"amount": 20000, "hour": 14, "is_domestic": True, "category_idx": 1},
            {"amount": 30000, "hour": 18, "is_domestic": False, "category_idx": 2},
        ])

        out = dump_all_models()
        assert out["cluster"] is True
        assert out["anomaly"] is True

        paths = bundle_paths()
        assert Path(paths["cluster"]).is_file()
        assert Path(paths["anomaly"]).is_file()
        assert Path(paths["dir"]) == Path(td)

        # 메모리 모델 초기화 후 load
        loaded = load_all_models()
        assert loaded["cluster"] is True
        assert cluster_model.model is not None


def test_load_missing_files_returns_false(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("ML_BUNDLE_DIR", td)
        from app.ml.persistence import load_all_models
        out = load_all_models()
        assert out == {
            "cluster": False, "anomaly": False,
            "classifier": False, "forecaster": False,
        }
