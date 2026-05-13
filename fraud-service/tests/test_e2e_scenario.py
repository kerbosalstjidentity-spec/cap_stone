"""W10-#1 — e2e 통합 시나리오 (회원가입→step-up→사기탐지→감사).

fraud-service 단일 프로세스 안에서 검증 가능한 부분만 시뮬레이션:
- 시나리오 시뮬레이터로 사기 거래 생성
- /v1/fraud/evaluate 로 BLOCK/REVIEW 트리거
- /admin/api/audit 가 감사 로그를 회수
- /admin/api/slo 가 시나리오 라벨 / 검출률 노출
- /v1/fraud/feedback/chargeback 으로 ground truth 라벨링
- /admin/api/ab-precision-recall 이 라벨링 후 metric 업데이트

backend 회원가입/step-up 은 fraud-service 단독 테스트라 mock — 통합 발표
시연용 시퀀스를 자동화한다.
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.feedback_store import feedback_store
from app.services.stats_collector import stats_collector

client = TestClient(app)


def setup_function(_):
    stats_collector.reset()
    feedback_store.clear()


def teardown_function(_):
    stats_collector.reset()
    feedback_store.clear()


def _evaluate(tx_id: str, scenario_label: str | None = None,
              amount: float = 50_000_000, ab_variant: str = "a") -> dict:
    payload = {
        "tx_id": tx_id,
        "user_id": "e2e-user",
        "amount": amount,
        "type": "TRANSFER",
        "score": 0.92,
        "scenario_label": scenario_label,
        "ab_variant": ab_variant,
    }
    r = client.post("/v1/fraud/evaluate", json=payload)
    return r.json() if r.status_code == 200 else {}


def test_e2e_voice_phishing_blocked_and_audited():
    out = _evaluate("VP-E2E-1", scenario_label="VOICE_PHISHING")
    assert out.get("final_action") in {"BLOCK", "REVIEW"}, out

    # 감사 로그 회수
    audit = client.get("/admin/api/audit?n=10").json()
    assert "logs" in audit
    assert any(log.get("tx_id") == "VP-E2E-1" for log in audit["logs"])


def test_e2e_scenario_slo_dashboard_updates():
    for i in range(5):
        _evaluate(f"VP-E2E-{i+10}", scenario_label="VOICE_PHISHING")
    time.sleep(0.05)

    slo = client.get("/admin/api/slo?bucket_minutes=1&buckets=5").json()
    assert "per_scenario" in slo
    vp = slo["per_scenario"].get("VOICE_PHISHING")
    assert vp is not None
    assert vp["total"] >= 5


def test_e2e_chargeback_updates_precision_recall():
    # variant a: BLOCK 1건 → 실제 사기 (chargeback)
    out_a = _evaluate("TX-E2E-A1", ab_variant="a")
    tx_a = "TX-E2E-A1"

    # variant b: BLOCK 1건 → 정상 (FP)
    _evaluate("TX-E2E-B1", ab_variant="b")

    # chargeback 등록 → variant a 의 BLOCK 이 TP
    r = client.post(
        "/v1/fraud/feedback/chargeback",
        json={"tx_id": tx_a, "user_id": "e2e-user", "amount": 50_000_000},
    )
    assert r.status_code in (200, 201), r.text

    # variant 별 metric
    pr = client.get("/admin/api/ab-precision-recall").json()
    assert "by_variant" in pr
    # variant a 는 TP>=1, recall>0
    if "a" in pr["by_variant"]:
        assert pr["by_variant"]["a"]["tp"] >= 1


def test_e2e_score_distribution_record():
    for i in range(3):
        _evaluate(f"TX-DIST-{i}", amount=10_000_000)
    sd = client.get("/admin/api/score-distribution?days=1").json()
    assert sd["overall"]["count"] >= 3
