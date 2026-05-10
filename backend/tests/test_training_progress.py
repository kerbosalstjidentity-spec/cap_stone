"""W6-#7 — 학습 진행 상태 추적 테스트 (status 분류 헬퍼)."""
from __future__ import annotations

from app.services.training_progress import classify_status_sync


def test_status_all_trained_is_success():
    out = classify_status_sync({
        "clustering": {"status": "trained"},
        "anomaly": {"status": "trained"},
        "classifier": {"status": "trained"},
        "forecaster": {"status": "trained"},
    })
    assert out == "success"


def test_status_some_skipped_is_partial():
    out = classify_status_sync({
        "clustering": {"status": "trained"},
        "anomaly": {"status": "skipped"},
    })
    assert out == "partial"


def test_status_none_trained_is_failed():
    out = classify_status_sync({
        "clustering": {"status": "skipped"},
        "anomaly": {"status": "skipped"},
    })
    assert out == "failed"


def test_status_ignores_persisted_key():
    out = classify_status_sync({
        "clustering": {"status": "trained"},
        "anomaly": {"status": "trained"},
        "classifier": {"status": "trained"},
        "forecaster": {"status": "trained"},
        "persisted": {"cluster": True, "anomaly": True},
    })
    assert out == "success"


def test_status_empty_is_success():
    assert classify_status_sync({}) == "success"


def test_status_unknown_value_is_failed():
    out = classify_status_sync({
        "clustering": "not-a-dict",
    })
    assert out == "failed"
