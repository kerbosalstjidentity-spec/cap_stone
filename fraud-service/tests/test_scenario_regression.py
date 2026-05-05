"""W5.5-#7 — 시나리오별 검출률 회귀 테스트 (≥80% 강건).

본 테스트는 W5.5-#1 의 합성기와 W5.5-#5 의 `classify_fraud_type` 매핑을
결합해 두 가지를 강하게 검증한다:

1) **검출률**: 시나리오당 100건에서 BLOCK+REVIEW 비율 ≥ 80%
2) **사기 유형 적중**: 시나리오당 dominant `fraud_type` 라벨이 기대 라벨과
   일치 (≥ 50% 점유 — 룰 기반이라 일부 NORMAL 섞임 허용)

velocity 의존 룰(MoneyMule 의 VELOCITY_FREQ, CardTesting 의 SPLIT_TXN)은
profile 누적 상태가 필요하므로, 테스트 setup 에서 `profile_store.ingest`
로 합성 거래 이력을 먼저 채워 룰이 발동할 조건을 만든다. 이 setup 은
W6.5 그래프 피처가 도착하면 자연스럽게 대체된다.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pytest

from app.services.fraud_service import FraudServiceManager
from app.services.policy_merge import classify_fraud_type
from app.services.profile_store import profile_store
from app.services.scenario_generator import generate

DETECTION_FLOOR = 0.80
DOMINANT_FRAUD_TYPE_FLOOR = 0.50

EXPECTED_DOMINANT_FRAUD_TYPE = {
    "VOICE_PHISHING": "VOICE_PHISHING",
    "MONEY_MULE": "MONEY_MULE",
    "ACCOUNT_TAKEOVER": "ACCOUNT_TAKEOVER",
    "CARD_TESTING": "CARD_TESTING",
}


def _seed_profile_velocity(user_id: str, count: int, window_seconds: int) -> None:
    """``profile_store`` 에 ``count`` 건의 최근 거래를 합성해 velocity 카운터를 끌어올린다."""
    now = datetime.now(tz=timezone.utc)
    for i in range(count):
        # 모두 같은 윈도우 내 시점 — 1m / 5m 카운터에 모두 잡히도록 분산
        ts = now.replace(microsecond=(i * 10_000) % 1_000_000)
        profile_store.ingest(user_id, {
            "tx_id": f"seed-{user_id}-{i}",
            "amount": 1_500_000,
            "timestamp": ts.isoformat(),
            "merchant_id": f"M-seed-{i}",
            "device_id": f"dev-seed-{user_id}",
            "hour": ts.hour,
        })


@pytest.fixture(autouse=True)
def _setup_profiles():
    """MoneyMule (5명) / CardTesting (3명) 의 user_id 에 velocity 시드 — VELOCITY_FREQ/SPLIT_TXN 발동 조건."""
    # MoneyMule — VelocityRule 5m 윈도우 ≥3 필요
    for i in range(5):
        _seed_profile_velocity(f"mule_{i}", count=6, window_seconds=300)
    # CardTesting — SplitTransactionRule 1m 윈도우 ≥5 필요 (소액 ≤100k)
    for i in range(3):
        _seed_profile_velocity(f"ct_attacker_{i}", count=8, window_seconds=60)
    yield
    # cleanup
    for i in range(5):
        profile_store.delete(f"mule_{i}")
    for i in range(3):
        profile_store.delete(f"ct_attacker_{i}")


def _evaluate(tx: dict) -> tuple[str, str]:
    """단건을 평가해 (final_action, fraud_type) 반환."""
    manager = FraudServiceManager(tx)
    final_action = manager.get_final_action()
    _, rule_ids = manager.get_rule_action()
    triggered = rule_ids.split(",") if rule_ids else []
    fraud_type = classify_fraud_type(triggered)
    return final_action, fraud_type


@pytest.mark.parametrize("scenario", list(EXPECTED_DOMINANT_FRAUD_TYPE.keys()))
def test_scenario_detection_rate_above_floor(scenario):
    txs = generate(scenario, count=100, seed=42)
    actions = [_evaluate(tx)[0] for tx in txs]
    detected = sum(1 for a in actions if a in ("BLOCK", "REVIEW"))
    rate = detected / len(actions)
    assert rate >= DETECTION_FLOOR, (
        f"{scenario} detection_rate={rate:.2%} < {DETECTION_FLOOR:.0%} "
        f"(BLOCK={actions.count('BLOCK')} REVIEW={actions.count('REVIEW')} "
        f"SOFT_REVIEW={actions.count('SOFT_REVIEW')} PASS={actions.count('PASS')})"
    )


@pytest.mark.parametrize("scenario,expected", list(EXPECTED_DOMINANT_FRAUD_TYPE.items()))
def test_scenario_dominant_fraud_type(scenario, expected):
    txs = generate(scenario, count=100, seed=42)
    fraud_types = [_evaluate(tx)[1] for tx in txs]
    counts = Counter(fraud_types)
    dominant, dominant_count = counts.most_common(1)[0]
    rate = dominant_count / len(fraud_types)
    assert dominant == expected, (
        f"{scenario}: dominant fraud_type={dominant} (rate={rate:.2%}), expected={expected}. "
        f"distribution={dict(counts)}"
    )
    assert rate >= DOMINANT_FRAUD_TYPE_FLOOR, (
        f"{scenario}: dominant {dominant} rate={rate:.2%} < {DOMINANT_FRAUD_TYPE_FLOOR:.0%}. "
        f"distribution={dict(counts)}"
    )


def test_overall_detection_table_matches_floor():
    """집계 검증 — 4종 평균 검출률 ≥ 80%."""
    total = 0
    detected = 0
    for scenario in EXPECTED_DOMINANT_FRAUD_TYPE:
        txs = generate(scenario, count=100, seed=42)
        actions = [_evaluate(tx)[0] for tx in txs]
        total += len(actions)
        detected += sum(1 for a in actions if a in ("BLOCK", "REVIEW"))
    overall = detected / total
    assert overall >= DETECTION_FLOOR, f"overall detection_rate={overall:.2%} < {DETECTION_FLOOR:.0%}"
