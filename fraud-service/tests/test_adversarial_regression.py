"""W7.5-#5 — 적대적 회귀 테스트 (정교한 회피 패턴).

W5.5-#7 (test_scenario_regression.py) 의 단순 시나리오는 사기범이 룰을 인지하기
*전* 의 행동 패턴이다. 본 파일은 사기범이 다음을 안다고 가정한 *적대적*(adversarial)
시나리오를 회귀 검증한다:

  1) **정교한 머니뮬 체인** — A→B→C→D 다단계 layering, 각 중간 노드가 받자마자
     ~95% 통과 송금 (단순 hub-spoke 가 아니라 *체인*; W6.5-#4 LayeringRule 회귀)
  2) **Smurfing (소액 분할)** — 큰 금액(5M)을 50건 100K 로 분할해 AMOUNT_REVIEW
     (≥1M) 회피 시도. SplitTransactionRule(1m 내 ≥5건 ∧ ≤100K) 가 잡아야 함.
  3) **CASH_OUT 분할 (BalanceDrain 회피)** — 잔액 2M 을 4번의 500K CASH_OUT 으로
     분할해 BalanceDrainRule(drain≥90%) 단일-거래 회피. 누적 velocity 가 잡아야 함.

각 패턴은 정확한 회피 의도를 갖고 설계됐으며 — 시스템이 *방어 라인을 어떻게
유지하는지* (어떤 룰이 백업으로 작동하는지) 명시적으로 측정한다. 검출 실패는
회귀 — 실패 시 어느 룰이 깨졌는지 추적할 수 있도록 행동 분포를 출력.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.fraud_service import FraudServiceManager
from app.services.graph_store import graph_store
from app.services.policy_merge import classify_fraud_type
from app.services.profile_store import profile_store

_client = TestClient(app)

DETECTION_FLOOR = 0.80


def _evaluate(tx: dict) -> tuple[str, str, str]:
    """단건 → (final_action, rule_ids, fraud_type). FraudServiceManager 직접 호출."""
    manager = FraudServiceManager(tx)
    final = manager.get_final_action()
    _, rule_ids = manager.get_rule_action()
    triggered = rule_ids.split(",") if rule_ids else []
    fraud_type = classify_fraud_type(triggered)
    return final, rule_ids, fraud_type


def _evaluate_via_api(tx: dict) -> tuple[str, str, str]:
    """API 경로 — ``/v1/fraud/evaluate`` 가 graph_features 자동 주입.

    체인/허브 룰처럼 graph_store 의존 룰은 이 경로를 써야 한다.
    """
    r = _client.post("/v1/fraud/evaluate", json=tx)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("final_action", ""), body.get("rule_id", "") or "", body.get("fraud_type", "")


def _seed_recent_history(user_id: str, count: int, *, amount: float, base_age_seconds: float = 30.0) -> None:
    """``profile_store`` 에 최근 거래를 채워 velocity 카운터를 끌어올린다."""
    now = datetime.now(tz=timezone.utc)
    for i in range(count):
        ts = now - timedelta(seconds=base_age_seconds + i)
        profile_store.ingest(user_id, {
            "tx_id": f"adv-seed-{user_id}-{i}",
            "amount": amount,
            "timestamp": ts.isoformat(),
            "merchant_id": f"M-adv-{i}",
            "device_id": f"dev-adv-{user_id}",
            "hour": ts.hour,
        })


# ---------------------------------------------------------------------------
# 1) 정교한 머니뮬 체인 — A → B → C → D layering
# ---------------------------------------------------------------------------

@pytest.fixture
def _mule_chain_setup():
    """A→B→C→D 체인 시뮬레이션. 각 중간 노드(B,C)는 받은 직후 ~95% 통과 송금."""
    nodes = ["adv_A", "adv_B", "adv_C", "adv_D"]
    graph_store.clear(nodes=nodes)
    now = time.time()
    # A → B: 1분 전 1,000,000
    graph_store.record("adv_A", "adv_B", 1_000_000.0, ts=now - 60)
    # B → C: 30초 전 950,000 (95% 통과)
    graph_store.record("adv_B", "adv_C", 950_000.0, ts=now - 30)
    # C → D: 10초 전 900,000 (94.7% 통과)
    graph_store.record("adv_C", "adv_D", 900_000.0, ts=now - 10)
    yield nodes
    graph_store.clear(nodes=nodes)


def test_adversarial_mule_chain_middle_nodes_detected(_mule_chain_setup):
    """체인 중간 노드(B, C) 의 다음 송금은 LAYERING_CHAIN 으로 검출."""
    detected = 0
    distribution: list[tuple[str, str]] = []
    for sender in ("adv_B", "adv_C"):
        # 각 중간 노드가 또 다른 거래(예: 새 수취인) 시도
        tx = {
            "tx_id": f"ADV-MULE-{sender}",
            "user_id": sender,
            "receiver_id": f"new_recv_{sender}",
            "score": 0.4,
            "amount": 200_000,  # 작아도 layering 룰은 그래프 시그널만 봄
            "type": "TRANSFER",
        }
        action, rule_ids, fraud_type = _evaluate_via_api(tx)
        distribution.append((sender, f"{action}/{rule_ids}/{fraud_type}"))
        if action in ("BLOCK", "REVIEW") and (
            "LAYERING_CHAIN" in rule_ids or "MONEY_MULE_HUB" in rule_ids
        ):
            detected += 1
    assert detected == 2, (
        f"체인 중간 노드 적대적 검출 실패: {detected}/2. distribution={distribution}"
    )


def test_adversarial_mule_chain_fraud_type_money_mule(_mule_chain_setup):
    """체인 중간 노드 발동 시 fraud_type=MONEY_MULE 라벨 일관성."""
    tx = {
        "tx_id": "ADV-MULE-LABEL",
        "user_id": "adv_B",
        "receiver_id": "new_recv_B_label",
        "score": 0.3,
        "amount": 150_000,
        "type": "TRANSFER",
    }
    _, rule_ids, fraud_type = _evaluate_via_api(tx)
    assert "LAYERING_CHAIN" in rule_ids or "MONEY_MULE_HUB" in rule_ids, rule_ids
    assert fraud_type == "MONEY_MULE", f"라벨 불일치: {fraud_type} (rule_ids={rule_ids})"


# ---------------------------------------------------------------------------
# 2) Smurfing — 큰 금액을 다건 100K 로 분할 (AMOUNT_REVIEW 회피)
# ---------------------------------------------------------------------------

SMURF_USER = "adv_smurf_attacker"


@pytest.fixture
def _smurf_setup():
    """1분 내 8건 100K 시드 — 다음 거래에서 SPLIT_TXN(1m≥5) 발동 환경."""
    profile_store.delete(SMURF_USER)
    _seed_recent_history(SMURF_USER, count=8, amount=100_000, base_age_seconds=5)
    yield
    profile_store.delete(SMURF_USER)


def test_adversarial_smurfing_split_txn_catches(_smurf_setup):
    """100K 짜리 분할 송금 — AMOUNT_REVIEW(1M) 미만이지만 SPLIT_TXN 으로 검출."""
    txs = [
        {
            "tx_id": f"ADV-SMURF-{i:02d}",
            "user_id": SMURF_USER,
            "score": 0.20,
            "amount": 100_000,
            "hour": datetime.now(tz=timezone.utc).hour,
            "is_foreign_ip": False,
            "ip": "10.0.0.5",
            "merchant_id": f"M-smurf-{i}",
            "device_id": "dev_smurf",
        }
        for i in range(20)
    ]
    actions = []
    rule_hits = Counter()
    for tx in txs:
        action, rule_ids, _ = _evaluate(tx)
        actions.append(action)
        for r in rule_ids.split(",") if rule_ids else []:
            rule_hits[r] += 1
    detected = sum(1 for a in actions if a in ("BLOCK", "REVIEW"))
    rate = detected / len(actions)
    assert rate >= DETECTION_FLOOR, (
        f"smurfing detection_rate={rate:.2%} < {DETECTION_FLOOR:.0%}. "
        f"actions={Counter(actions)}, rules={dict(rule_hits)}"
    )
    assert "SPLIT_TXN" in rule_hits, f"SPLIT_TXN 미발동: {dict(rule_hits)}"


# ---------------------------------------------------------------------------
# 3) CASH_OUT 분할 — BalanceDrainRule(drain≥90%) 단일-거래 회피
# ---------------------------------------------------------------------------

CASH_SPLIT_USER = "adv_cash_split"


@pytest.fixture
def _cash_split_setup():
    """공격자가 잔액 2M 을 4×500K 로 나눠 인출 — 각 단건은 25% drain (룰 회피).

    방어선: 같은 사용자 누적 velocity (5m 윈도우 ≥3) 가 백업으로 발동해야 함.
    이를 시뮬레이션하기 위해 직전 5분 내 거래 5건을 시드.
    """
    profile_store.delete(CASH_SPLIT_USER)
    _seed_recent_history(CASH_SPLIT_USER, count=5, amount=500_000, base_age_seconds=30)
    yield
    profile_store.delete(CASH_SPLIT_USER)


def test_adversarial_cash_out_split_caught_by_velocity(_cash_split_setup):
    """단건 BalanceDrainRule 회피 — velocity 가 백업 검출."""
    # 다음 분할 인출. 각 단건은 25% drain → BalanceDrainRule 미발동 (정상 동작).
    tx = {
        "tx_id": "ADV-CASH-SPLIT-1",
        "user_id": CASH_SPLIT_USER,
        "score": 0.30,
        "type": "CASH_OUT",
        "amount": 500_000,
        "oldbalanceOrg": 2_000_000,
        "newbalanceOrig": 1_500_000,  # 25% drain only
        "hour": datetime.now(tz=timezone.utc).hour,
        "ip": "10.0.0.7",
        "merchant_id": "M-cash-split",
        "device_id": "dev_cash_split",
    }
    action, rule_ids, _ = _evaluate(tx)
    # 1) BalanceDrainRule 단독으로는 미발동이어야 함 (회피 성공)
    assert "BALANCE_DRAIN" not in rule_ids, (
        f"단건 25% drain 인데 BALANCE_DRAIN 오발동: {rule_ids}"
    )
    # 2) 하지만 velocity 누적으로 백업 검출되어야 함
    assert action in ("BLOCK", "REVIEW"), (
        f"분할 회피 미검출 (회귀): action={action}, rule_ids={rule_ids}"
    )
    assert "VELOCITY_FREQ" in rule_ids, (
        f"velocity 백업 라인 미작동: rule_ids={rule_ids}"
    )


def test_adversarial_cash_out_split_single_low_drain_no_block_drain():
    """공격자가 1건만 시도 (velocity 시드 없음) → BalanceDrainRule 회피 성공
    + velocity 도 미발동 → PASS/SOFT_REVIEW. 이 테스트는 *현재 시스템의 한계*를
    문서화 — chargeback 피드백 루프(W7.5-#4)/시퀀스 모델(W7.5-#2) 도착 시 바뀜.
    """
    profile_store.delete("adv_cash_solo")
    tx = {
        "tx_id": "ADV-CASH-SOLO",
        "user_id": "adv_cash_solo",
        "score": 0.20,
        "type": "CASH_OUT",
        "amount": 500_000,
        "oldbalanceOrg": 2_000_000,
        "newbalanceOrig": 1_500_000,
        "hour": 14,
        "merchant_id": "M-solo",
    }
    action, rule_ids, _ = _evaluate(tx)
    assert "BALANCE_DRAIN" not in rule_ids
    # 알려진 한계: 단발성 25% drain 은 현재 미검출. 회귀 테스트로 명시.
    assert action in ("PASS", "SOFT_REVIEW"), (
        f"예상치 못한 검출 — 새 룰이 들어왔다면 본 테스트 갱신 필요: "
        f"action={action}, rule_ids={rule_ids}"
    )
