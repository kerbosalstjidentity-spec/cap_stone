"""사기 시나리오 합성기 (W5.5-#1).

블로그 12 §Track 2 — 4종 시나리오(보이스피싱·머니뮬·계정탈취·카드테스팅) 트랜잭션을
합성해 검출률(=BLOCK+REVIEW 비율)을 측정하기 위한 입력을 생성한다.

PaySim 도입(W5.5-#2~#3) 전 단계 — 현 입력 스키마(``FraudEvaluateRequest`` 호환 dict)
그대로 발생시키며, 룰엔진 상태(velocity, profile)를 요구하지 않는 stateless 시그널에
의존한다. 그래프·시퀀스 의존 시나리오는 W6.5/W7.5 에서 보강한다.
"""
from __future__ import annotations

import random
from typing import Iterable

SCENARIO_TYPES: tuple[str, ...] = (
    "VOICE_PHISHING",
    "MONEY_MULE",
    "ACCOUNT_TAKEOVER",
    "CARD_TESTING",
)


def _voice_phishing(rng: random.Random, idx: int) -> dict:
    # 야간(02~04시) 고액 송금 — AmountBlockRule(≥5M) + TimeRiskRule + 높은 score
    return {
        "tx_id": f"VP-{idx:04d}",
        "user_id": f"vp_user_{idx % 30}",
        "score": round(rng.uniform(0.70, 0.99), 4),
        "amount": float(rng.randint(5_000_000, 30_000_000)),
        "hour": rng.choice([2, 3, 4, 23]),
        "is_foreign_ip": False,
        "ip": f"10.0.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        "merchant_id": f"M-NEW-{rng.randint(900, 999)}",
        "device_id": f"dev_vp_{idx}",
    }


def _money_mule(rng: random.Random, idx: int) -> dict:
    # 중간 금액 반복 송금 — AmountReviewRule(≥1M) + score
    # (실제 hub-spoke 그래프 시그널은 W6.5 graph_features.py 가 담당)
    return {
        "tx_id": f"MM-{idx:04d}",
        "user_id": f"mule_{idx % 5}",  # 5명에 집중 → 후속 W6.5 fan-in 측정용
        "score": round(rng.uniform(0.40, 0.85), 4),
        "amount": float(rng.randint(1_000_000, 3_000_000)),
        "hour": rng.randint(9, 22),
        "is_foreign_ip": False,
        "ip": f"172.16.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        "merchant_id": f"M-MULE-{rng.randint(100, 199)}",
        "device_id": f"dev_mule_{idx % 5}",
    }


def _account_takeover(rng: random.Random, idx: int) -> dict:
    # 해외 IP + 새 device + 큰 금액 — ForeignIpRule + score
    return {
        "tx_id": f"ATO-{idx:04d}",
        "user_id": f"ato_user_{idx % 50}",
        "score": round(rng.uniform(0.60, 0.95), 4),
        "amount": float(rng.randint(500_000, 3_000_000)),
        "hour": rng.randint(0, 23),
        "is_foreign_ip": True,
        "ip": f"203.0.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        "merchant_id": f"M-{rng.randint(1, 200)}",
        "device_id": f"dev_NEW_{idx}",  # 매 거래 새 device
    }


def _card_testing(rng: random.Random, idx: int) -> dict:
    # 소액 다건 — score(REVIEW threshold 0.35↑)에 의존
    # (1분 내 velocity 시그널은 W6.5/W7.5 에서 profile 누적 후 보강)
    return {
        "tx_id": f"CT-{idx:04d}",
        "user_id": f"ct_attacker_{idx % 3}",
        "score": round(rng.uniform(0.40, 0.75), 4),
        "amount": float(rng.randint(1_000, 10_000)),
        "hour": rng.randint(0, 23),
        "is_foreign_ip": rng.random() < 0.3,
        "ip": f"198.51.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        "merchant_id": f"M-{rng.randint(1, 50)}",
        "device_id": f"dev_ct_{idx % 3}",
    }


_BUILDERS = {
    "VOICE_PHISHING": _voice_phishing,
    "MONEY_MULE": _money_mule,
    "ACCOUNT_TAKEOVER": _account_takeover,
    "CARD_TESTING": _card_testing,
}


def _voice_phishing_paysim(rng: random.Random, idx: int) -> dict:
    # 보이스피싱: 큰 금액 TRANSFER, 잔액 거의 전부 빠짐
    amount = float(rng.randint(5_000_000, 30_000_000))
    old = amount + rng.randint(0, 100_000)
    return {
        "tx_id": f"VP-PS-{idx:04d}",
        "user_id": f"vp_user_{idx % 30}",
        "type": "TRANSFER",
        "amount": amount,
        "oldbalanceOrg": old,
        "newbalanceOrig": old - amount,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0,
        "nameDest": f"C{rng.randint(100000, 999999)}",
        "step": rng.randint(1, 743),
    }


def _money_mule_paysim(rng: random.Random, idx: int) -> dict:
    # 머니뮬: TRANSFER 받은 직후 같은 금액 CASH_OUT — 통과 패턴
    amount = float(rng.randint(1_000_000, 3_000_000))
    return {
        "tx_id": f"MM-PS-{idx:04d}",
        "user_id": f"mule_{idx % 5}",
        "type": "CASH_OUT",
        "amount": amount,
        "oldbalanceOrg": amount,
        "newbalanceOrig": 0.0,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0,  # destination 잔액 미반영
        "nameDest": f"C{rng.randint(100000, 999999)}",
        "step": rng.randint(1, 743),
    }


def _account_takeover_paysim(rng: random.Random, idx: int) -> dict:
    # 계정탈취: 큰 금액 TRANSFER, 잔액 변화 의심
    amount = float(rng.randint(500_000, 3_000_000))
    old = amount + rng.randint(10_000, 500_000)
    return {
        "tx_id": f"ATO-PS-{idx:04d}",
        "user_id": f"ato_user_{idx % 50}",
        "type": "TRANSFER",
        "amount": amount,
        "oldbalanceOrg": old,
        "newbalanceOrig": old - amount,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0,
        "nameDest": f"C{rng.randint(100000, 999999)}",
        "step": rng.randint(1, 743),
    }


def _card_testing_paysim(rng: random.Random, idx: int) -> dict:
    # 카드테스팅: 소액 다건 TRANSFER (PaySim 에선 PAYMENT 가 사기 없음 → TRANSFER 사용)
    amount = float(rng.randint(1_000, 10_000))
    old = float(rng.randint(50_000, 500_000))
    return {
        "tx_id": f"CT-PS-{idx:04d}",
        "user_id": f"ct_attacker_{idx % 3}",
        "type": "TRANSFER",
        "amount": amount,
        "oldbalanceOrg": old,
        "newbalanceOrig": old - amount,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0,
        "nameDest": f"C{rng.randint(100000, 999999)}",
        "step": rng.randint(1, 743),
    }


_BUILDERS_PAYSIM = {
    "VOICE_PHISHING": _voice_phishing_paysim,
    "MONEY_MULE": _money_mule_paysim,
    "ACCOUNT_TAKEOVER": _account_takeover_paysim,
    "CARD_TESTING": _card_testing_paysim,
}


def generate(scenario: str, count: int = 100, seed: int = 42, *, paysim_raw: bool = False) -> list[dict]:
    """단일 시나리오의 합성 트랜잭션 ``count`` 건을 결정적으로 생성.

    Args:
        scenario: 4종 중 하나
        count: 생성 건수
        seed: 결정적 합성 시드
        paysim_raw: True 면 PaySim 원본 컬럼(type, amount, oldbalanceOrg, ...)
            출력 — 모델까지 통과하는 회귀 검증용. False(기본)는 score 가
            미리 합성된 evaluate-입력 형식 (기존 W5.5-#1 호환).
    """
    if scenario not in SCENARIO_TYPES:
        raise ValueError(f"unknown scenario: {scenario}. expected one of {SCENARIO_TYPES}")
    rng = random.Random(f"{scenario}:{seed}:{'raw' if paysim_raw else 'eval'}")
    builders = _BUILDERS_PAYSIM if paysim_raw else _BUILDERS
    return [builders[scenario](rng, i) for i in range(count)]


def generate_all(
    scenarios: Iterable[str] | None = None,
    count: int = 100,
    seed: int = 42,
    *,
    paysim_raw: bool = False,
) -> dict[str, list[dict]]:
    """여러 시나리오를 한 번에 합성."""
    targets = tuple(scenarios) if scenarios else SCENARIO_TYPES
    return {s: generate(s, count=count, seed=seed, paysim_raw=paysim_raw) for s in targets}
