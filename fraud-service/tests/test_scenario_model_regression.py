"""W5.5-audit — 모델까지 통과하는 시나리오 회귀.

W5.5-#7 의 강건 회귀는 score 가 미리 주입된 evaluate 입력으로 룰·정책만
검증했다. 본 테스트는 한 단계 더 들어가 ``scenario_generator(paysim_raw=True)``
가 PaySim 원본 컬럼만 합성 → ``/v1/score`` (paysim 도메인 분기) → RF 가
산출한 ``fraud_probability`` ≥ block_min 비율을 검증한다.

PaySim 운영 번들이 실제로 4종 시나리오를 잡는가에 답한다.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import pytest

from app.services.scenario_generator import SCENARIO_TYPES, generate

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYSIM_BUNDLE = REPO_ROOT / "fds-research" / "outputs" / "fds" / "model_bundle_paysim_time_clean.joblib"

# 시나리오별 모델 단독 검출 기대치.
# PaySim 학습 분포(TRANSFER+CASH_OUT 대형 금액)에 따라 모델 커버리지가 다르다:
# - VOICE_PHISHING / MONEY_MULE / ACCOUNT_TAKEOVER: 큰 금액·잔액 모순 패턴 → 모델 잘 잡음
# - CARD_TESTING: 소액 다건 — PaySim 학습 데이터에 해당 패턴 부재. 모델 단독 검출 불가.
#   룰 엔진(VelocityRule + SplitTransactionRule) 이 보완 (W5.5-#7 회귀 100% 검출).
MODEL_DETECTION_FLOOR_BY_SCENARIO: dict[str, float] = {
    "VOICE_PHISHING": 0.80,
    "MONEY_MULE": 0.80,
    "ACCOUNT_TAKEOVER": 0.80,
    "CARD_TESTING": 0.00,  # 모델 단독으론 못 잡음 — 룰 엔진이 메움
}


@pytest.fixture(scope="module")
def paysim_bundle():
    if not PAYSIM_BUNDLE.exists():
        pytest.skip(f"paysim bundle absent at {PAYSIM_BUNDLE}")
    return joblib.load(PAYSIM_BUNDLE)


@pytest.mark.parametrize("scenario", list(SCENARIO_TYPES))
def test_model_detects_scenario(scenario, paysim_bundle):
    """raw paysim 입력 → score_paysim_bundle 추론 → 시나리오 100건 중
    fraud_probability 큐 진입(≥review_min) 비율을 도메인 기대치와 비교."""
    from app.scoring.ensemble import score_paysim_bundle
    from app.scoring.features import paysim_dict_to_matrix

    txs = generate(scenario, count=100, seed=42, paysim_raw=True)
    raw_names = paysim_bundle["raw_feature_names"]
    block_min = float(paysim_bundle.get("block_min", 0.95))
    review_min = float(paysim_bundle.get("review_min", 0.35))

    block = 0
    queue = 0
    for tx in txs:
        X = paysim_dict_to_matrix(tx, raw_names)
        out = score_paysim_bundle(paysim_bundle, X)
        p = out["fraud_probability"]
        if p >= block_min:
            block += 1
        if p >= review_min:
            queue += 1

    queue_rate = queue / len(txs)
    floor = MODEL_DETECTION_FLOOR_BY_SCENARIO[scenario]
    assert queue_rate >= floor, (
        f"{scenario}: model queue rate={queue_rate:.2%} < {floor:.0%} "
        f"(block={block}, queue={queue}/100, block_min={block_min}, review_min={review_min})"
    )


def test_card_testing_documented_model_gap(paysim_bundle):
    """CARD_TESTING 이 모델 단독으로 안 잡힌다는 사실을 명시적으로 문서화.

    PaySim 학습 데이터에 소액 다건 사기 패턴이 없음 → 모델 입장에선 정상.
    룰 엔진(VelocityRule + SplitTransactionRule) 이 detection 을 책임진다.
    """
    from app.scoring.ensemble import score_paysim_bundle
    from app.scoring.features import paysim_dict_to_matrix

    txs = generate("CARD_TESTING", count=100, seed=42, paysim_raw=True)
    raw_names = paysim_bundle["raw_feature_names"]
    review_min = float(paysim_bundle.get("review_min", 0.35))
    queue = sum(
        1 for tx in txs
        if score_paysim_bundle(paysim_bundle, paysim_dict_to_matrix(tx, raw_names))["fraud_probability"]
        >= review_min
    )
    # 0% 보장 — 만약 모델이 카드테스팅을 잡기 시작했다면 학습 분포가 바뀐 신호
    assert queue == 0, (
        f"카드테스팅 패턴을 모델이 {queue}/100 건 잡음 — 학습 분포 변경됐을 수 있음. "
        "MODEL_DETECTION_FLOOR_BY_SCENARIO['CARD_TESTING'] 갱신 검토."
    )
