"""W7.5-#2 — 사용자 시퀀스 점수 (직전 N건 대비 이상도) 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring.sequence_score import (
    MIN_HISTORY_FOR_SCORE,
    SeqEvent,
    score_sequence,
    sequence_store,
)

client = TestClient(app)


def test_cold_start_returns_zero():
    res = score_sequence("u_new", current_amount=1_000_000, current_hour=14)
    assert res["cold_start"] is True
    assert res["sequence_score"] == 0.0


def test_normal_sequence_low_score():
    """평소와 비슷한 amount + 친숙한 hour → 낮은 score."""
    history = [SeqEvent(amount=100_000 + i * 1000, hour=14) for i in range(MIN_HISTORY_FOR_SCORE + 5)]
    res = score_sequence("u1", current_amount=102_000, current_hour=14, history=history)
    assert res["cold_start"] is False
    assert res["sequence_score"] < 0.3
    assert res["hour_anomaly"] == 0.0


def test_amount_spike_high_z():
    history = [SeqEvent(amount=100_000, hour=14) for _ in range(10)]
    res = score_sequence("u2", current_amount=10_000_000, current_hour=14, history=history)
    # 표준편차 0(상수) 면 z=0, 작은 노이즈 추가 시 z 큰 값
    history = [SeqEvent(amount=100_000 + (i % 3) * 1000, hour=14) for i in range(10)]
    res = score_sequence("u2", current_amount=10_000_000, current_hour=14, history=history)
    assert res["amount_z"] > 4
    assert res["sequence_score"] >= 0.7


def test_unfamiliar_hour_raises_score():
    history = [SeqEvent(amount=100_000, hour=14) for _ in range(10)]
    res = score_sequence("u3", current_amount=100_000, current_hour=3, history=history)
    assert res["hour_anomaly"] == 1.0
    assert res["sequence_score"] >= 0.3


def test_store_append_and_history():
    sequence_store.reset()
    for i in range(7):
        sequence_store.append("uX", amount=100_000 + i * 100, hour=10)
    assert sequence_store.length("uX") == 7
    hist = sequence_store.history("uX")
    assert len(hist) == 7
    assert all(e.hour == 10 for e in hist)


def test_store_max_history_clip():
    sequence_store.reset()
    for i in range(50):
        sequence_store.append("uClip", amount=i, hour=10)
    # default max_history=20
    assert sequence_store.length("uClip") <= 20


def test_evaluate_returns_sequence_score_field():
    sequence_store.reset()
    payload = {
        "tx_id": "SEQ-1",
        "score": 0.4,
        "amount": 100_000,
        "user_id": "u_seq",
        "hour": 14,
    }
    r = client.post("/v1/fraud/evaluate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "sequence_score" in body
    assert body["sequence_score"]["cold_start"] is True


def test_evaluate_warm_sequence():
    sequence_store.reset()
    # 동일 user_id 로 N+1번 호출 → 마지막 호출에서 cold_start=False 기대
    for i in range(MIN_HISTORY_FOR_SCORE + 1):
        client.post("/v1/fraud/evaluate", json={
            "tx_id": f"WARM-{i}",
            "score": 0.3,
            "amount": 50_000 + i * 10,
            "user_id": "u_warm",
            "hour": 14,
        })
    r = client.post("/v1/fraud/evaluate", json={
        "tx_id": "WARM-LAST",
        "score": 0.3,
        "amount": 50_100,
        "user_id": "u_warm",
        "hour": 14,
    })
    body = r.json()
    assert body["sequence_score"]["cold_start"] is False
    assert body["sequence_score"]["history_len"] >= MIN_HISTORY_FOR_SCORE
