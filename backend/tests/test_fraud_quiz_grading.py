"""W9-#1 — 사기 퀴즈 채점 정답 검증 버그 fix 단위 테스트.

라우터 의존(=sentry_sdk 등 main.py 의 ML 부트스트랩) 을 피하기 위해
pure helper(_fraud_correct_answer_map) 만 직접 호출.
"""
from __future__ import annotations

from app.api.routes_education import _FRAUD_SCENARIOS, _fraud_correct_answer_map


def test_correct_map_covers_all_scenarios():
    m = _fraud_correct_answer_map()
    assert len(m) == len(_FRAUD_SCENARIOS)
    for s in _FRAUD_SCENARIOS:
        expected = "의심 거래" if s["is_fraud"] else "정상 거래"
        assert m[s["id"]] == expected


def test_correct_map_returns_correct_label():
    m = _fraud_correct_answer_map()
    fraud_ids = [s["id"] for s in _FRAUD_SCENARIOS if s["is_fraud"]]
    normal_ids = [s["id"] for s in _FRAUD_SCENARIOS if not s["is_fraud"]]
    assert all(m[i] == "의심 거래" for i in fraud_ids)
    assert all(m[i] == "정상 거래" for i in normal_ids)


def test_grading_logic_simulation():
    """submit_fraud_quiz 채점 로직 시뮬레이션 — 잘못된 답은 카운트 X."""
    correct_map = _fraud_correct_answer_map()
    # FQ_001 (정상) 에 의심 거래 답 → 오답
    # FQ_002 (사기) 에 의심 거래 답 → 정답
    # FQ_003 (정상) 에 정상 거래 답 → 정답
    qids = ["FQ_001", "FQ_002", "FQ_003"]
    answers = ["의심 거래", "의심 거래", "정상 거래"]
    correct = sum(1 for q, a in zip(qids, answers) if correct_map.get(q) == a)
    assert correct == 2
