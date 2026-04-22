"""Admin API 확장 테스트 (규칙 토글, 임계값, 통계)."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_rules():
    r = client.get("/admin/api/rules")
    assert r.status_code == 200
    rules = r.json()["rules"]
    assert len(rules) >= 7
    rule_ids = {rule["rule_id"] for rule in rules}
    assert "AMOUNT_BLOCK" in rule_ids
    assert "VELOCITY_FREQ" in rule_ids


def test_toggle_rule():
    # 현재 상태 확인
    rules = client.get("/admin/api/rules").json()["rules"]
    original = next(r for r in rules if r["rule_id"] == "AMOUNT_REVIEW")["enabled"]

    r = client.post("/admin/api/rules/AMOUNT_REVIEW/toggle")
    assert r.status_code == 200
    assert r.json()["enabled"] != original

    # 원복
    client.post("/admin/api/rules/AMOUNT_REVIEW/toggle")


def test_toggle_unknown_rule():
    r = client.post("/admin/api/rules/NO_SUCH_RULE/toggle")
    assert r.status_code == 404


def test_set_threshold():
    r = client.patch("/admin/api/threshold", json={"BLOCK_THRESHOLD": 0.95})
    assert r.status_code == 200
    data = r.json()
    assert data["updated"]["BLOCK_THRESHOLD"] == 0.95
    # 원복
    client.patch("/admin/api/threshold", json={"BLOCK_THRESHOLD": 0.85})


def test_set_threshold_ignores_unknown_key():
    r = client.patch("/admin/api/threshold", json={"UNKNOWN_KEY": 999})
    assert r.status_code == 200
    assert "UNKNOWN_KEY" not in r.json()["updated"]


def test_stats_and_reset():
    # evaluate 한 건 실행해 통계 쌓기
    client.post("/v1/fraud/evaluate", json={"tx_id": "stat_tx", "score": 0.1, "amount": 5000})

    r = client.get("/admin/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_evaluated"] >= 1

    # 리셋
    r2 = client.delete("/admin/api/stats")
    assert r2.status_code == 200
    assert r2.json()["reset"] is True

    r3 = client.get("/admin/api/stats")
    assert r3.json()["total_evaluated"] == 0
