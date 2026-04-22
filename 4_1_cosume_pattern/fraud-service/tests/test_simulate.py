"""시뮬레이터 API 테스트."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_simulate_basic():
    r = client.post("/v1/simulate", json={"score": 0.9, "amount": 2_000_000})
    assert r.status_code == 200
    data = r.json()
    assert "final_action" in data
    assert "triggered_rules" in data
    assert "what_if" in data


def test_simulate_pass_case():
    # 프로파일 없는 신규 유저 + 소액 → model PASS, rule PASS
    r = client.post("/v1/simulate", json={"score": 0.0, "amount": 1_000, "user_id": "sim_new_user_xyz"})
    assert r.status_code == 200
    data = r.json()
    assert data["model_action"] == "PASS"
    # final_action은 rule 결과에 따라 달라질 수 있으므로 PASS or SOFT_REVIEW 허용
    assert data["final_action"] in ("PASS", "SOFT_REVIEW")


def test_simulate_block_case():
    r = client.post("/v1/simulate", json={"score": 0.95, "amount": 6_000_000})
    assert r.status_code == 200
    data = r.json()
    assert data["final_action"] == "BLOCK"


def test_simulate_batch():
    payload = {
        "scenarios": [
            {"label": "소액", "score": 0.1, "amount": 5_000},
            {"label": "대금액", "score": 0.5, "amount": 3_000_000},
            {"label": "고위험", "score": 0.95, "amount": 500_000},
        ]
    }
    r = client.post("/v1/simulate/batch", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    labels = [s["label"] for s in data["results"]]
    assert "소액" in labels


def test_threshold_sweep():
    r = client.get("/v1/simulate/threshold-sweep", params={"score": 0.75, "amount": 300_000})
    assert r.status_code == 200
    data = r.json()
    assert len(data["sweep"]) == 8
    # 임계값 0.5 → score 0.75는 BLOCK
    low_thresh = next(s for s in data["sweep"] if s["block_threshold"] == 0.50)
    assert low_thresh["model_action"] == "BLOCK"
    # 임계값 0.99 → score 0.75는 PASS 또는 REVIEW (0.75 < 0.99)
    high_thresh = next(s for s in data["sweep"] if s["block_threshold"] == 0.99)
    assert high_thresh["model_action"] != "BLOCK"
