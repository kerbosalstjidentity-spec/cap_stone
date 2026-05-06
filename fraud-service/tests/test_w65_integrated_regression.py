"""W6.5-#7 — 그래프 + 비용 통합 검출률 회귀.

W5.5-#7 의 룰만 회귀(100% MoneyMule 라벨 적중)에서 한 단계 더 들어가:
- graph_store hub-spoke 시드 후 100건 MONEY_MULE 시나리오를 평가해
  BLOCK+REVIEW 비율 ≥ 90% 강건 회귀.
- evaluate 응답에 W6.5 산출물(`graph_features`, `expected_loss`,
  `fraud_type`) 모두 노출되는지 필드 활성 검증.

baseline(그래프 비어) vs graph-aware 정량 비교는 본 테스트 범위 외 —
W6.5-#5 비용 가중 임계값만으로 baseline 이 saturation 되어 그래프
효과를 측정할 헤드룸이 없다. 비교 측정은 별도 벤치 스크립트
``scripts/bench_w65_graph_uplift.py`` (저금액 sweep) 로 분리.
"""
from __future__ import annotations

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.graph_store import graph_store
from app.services.scenario_generator import generate

client = TestClient(app)

MULE_USER_IDS = [f"mule_{i}" for i in range(5)]  # scenario_generator 의 user_id 패턴
EXIT_NODES = ["exit_a_w657", "exit_b_w657", "exit_c_w657"]
SHARED_VICTIMS = [f"victim_{i}_w657" for i in range(6)]


def _seed_mule_pattern() -> None:
    """각 mule_{i} 가 6명에게서 받고 90% 통과시킨 hub 패턴 — graph_store 시드."""
    for mule in MULE_USER_IDS:
        for v in SHARED_VICTIMS:
            graph_store.record(v, mule, 1000.0)
        graph_store.record(mule, EXIT_NODES[0], 1500.0)
        graph_store.record(mule, EXIT_NODES[1], 2000.0)
        graph_store.record(mule, EXIT_NODES[2], 1900.0)


def _clean_mule_pattern() -> None:
    nodes = MULE_USER_IDS + EXIT_NODES + SHARED_VICTIMS
    graph_store.clear(nodes=nodes)


def _evaluate_scenario(count: int = 100) -> Counter:
    txs = generate("MONEY_MULE", count=count, seed=42, paysim_raw=True)
    actions: Counter = Counter()
    for tx in txs:
        # paysim_raw 출력에는 score 가 없음 — evaluate 입력 형식으로 변환
        # (W5.5-#7 와 호환): receiver_id 로 nameDest 매핑.
        payload = {
            "tx_id": tx["tx_id"],
            "score": 0.45,  # baseline 대비 W6.5 효과를 보기 위해 의도적으로 낮은 score
            "amount": float(tx["amount"]),
            "user_id": tx["user_id"],
            "receiver_id": tx["nameDest"],
        }
        r = client.post("/v1/fraud/evaluate", json=payload)
        assert r.status_code == 200, r.text
        actions[r.json()["final_action"]] += 1
    return actions


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    # 100건 evaluate × 2회 = 200req — 기본 RATE_LIMIT_RPM(120) 초과. 테스트만 비활성.
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit, "_ENABLED", False)
    _clean_mule_pattern()
    yield
    _clean_mule_pattern()


def test_money_mule_detection_with_graph_seed_above_90():
    """그래프 시드 후 머니뮬 시나리오 BLOCK+REVIEW 비율 ≥ 90%."""
    _seed_mule_pattern()
    actions = _evaluate_scenario(count=100)
    queue = actions["BLOCK"] + actions["REVIEW"]
    rate = queue / 100
    assert rate >= 0.90, (
        f"MONEY_MULE detection={rate:.0%} < 90% (with graph seed). "
        f"distribution={dict(actions)}"
    )
    # block 승격이 실제 발생했는지도 확인 (BLOCK > 0)
    assert actions["BLOCK"] > 0


def test_w65_features_active_in_response():
    """evaluate 응답에 W6.5 산출물(graph_features, expected_loss) 모두 포함."""
    _seed_mule_pattern()
    r = client.post("/v1/fraud/evaluate", json={
        "tx_id": "W657-FEATCHK", "score": 0.45, "amount": 100_000,
        "user_id": "mule_0", "receiver_id": EXIT_NODES[0],
    })
    body = r.json()
    assert "graph_features" in body
    assert "expected_loss" in body
    assert "fraud_type" in body
    feats = body["graph_features"]
    assert feats["sender_fan_in_count"] >= 6  # 6명에게서 받은 시드
    assert feats["sender_pass_through_ratio"] >= 0.8
