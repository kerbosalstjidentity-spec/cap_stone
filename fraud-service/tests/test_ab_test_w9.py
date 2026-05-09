"""W9-#7 — A/B bundle_b 로드 실패 ERROR 로그 + soft_review 키 분리."""
from __future__ import annotations

import importlib
import logging
import os


def _reload(env: dict[str, str] | None = None):
    if env:
        for k, v in env.items():
            os.environ[k] = v
    from app.scoring import ab_test
    importlib.reload(ab_test)
    return ab_test


def test_load_bundle_b_no_path():
    os.environ.pop("MODEL_B_PATH", None)
    ab = _reload()
    assert ab.load_bundle_b() is None


def test_load_bundle_b_missing_file_logs_error(caplog):
    os.environ["MODEL_B_PATH"] = "/tmp/does_not_exist_paywise_xyz.joblib"
    try:
        ab = _reload()
        with caplog.at_level(logging.ERROR, logger="app.scoring.ab_test"):
            assert ab.load_bundle_b() is None
        assert any("파일 없음" in r.message or "로드 실패" in r.message for r in caplog.records)
    finally:
        os.environ.pop("MODEL_B_PATH", None)
        _reload()


def test_record_soft_review_separate_key():
    ab = _reload()
    ab.reset_stats()
    ab._record("a", "BLOCK")
    ab._record("a", "REVIEW")
    ab._record("a", "SOFT_REVIEW")
    ab._record("a", "SOFT_REVIEW")
    ab._record("a", "PASS")
    s = ab.get_stats()["a"]
    assert s["block"] == 1
    assert s["review"] == 1
    assert s["soft_review"] == 2
    assert s["pass"] == 1
    assert s["count"] == 5


def test_record_unknown_action_only_counts_total():
    ab = _reload()
    ab.reset_stats()
    ab._record("a", "MYSTERY")
    s = ab.get_stats()["a"]
    assert s["count"] == 1
    assert s["block"] == 0
    assert s["review"] == 0
    assert s["soft_review"] == 0
