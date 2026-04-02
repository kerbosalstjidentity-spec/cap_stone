"""Blacklist / Whitelist 테스트."""
from fastapi.testclient import TestClient
from app.main import app
from app.services.access_list import AccessListStore

client = TestClient(app)


# --- 단위 테스트 ---

def test_blacklist_user_id():
    store = AccessListStore()
    store.blacklist_add("user_id", "evil_user", "사기 의심")
    assert store.is_blacklisted(user_id="evil_user") is not None
    assert store.is_blacklisted(user_id="normal") is None


def test_blacklist_ip():
    store = AccessListStore()
    store.blacklist_add("ip", "1.2.3.4")
    assert store.is_blacklisted(ip="1.2.3.4") is not None
    assert store.is_blacklisted(ip="9.9.9.9") is None


def test_blacklist_remove():
    store = AccessListStore()
    store.blacklist_add("user_id", "u1")
    assert store.blacklist_remove("user_id", "u1") is True
    assert store.is_blacklisted(user_id="u1") is None
    assert store.blacklist_remove("user_id", "u1") is False


def test_whitelist():
    store = AccessListStore()
    store.whitelist_add("vip_user")
    assert store.is_whitelisted("vip_user") is True
    assert store.is_whitelisted("normal") is False
    store.whitelist_remove("vip_user")
    assert store.is_whitelisted("vip_user") is False


# --- API 테스트 ---

def test_blacklist_api_add_and_check():
    # 추가
    r = client.post("/admin/api/blacklist", json={"kind": "user_id", "value": "bad_actor", "reason": "테스트"})
    assert r.status_code == 201

    # 블랙리스트 목록 확인
    r2 = client.get("/admin/api/blacklist")
    values = [e["value"] for e in r2.json()["blacklist"]]
    assert "bad_actor" in values

    # 평가 시 BLOCK 처리
    r3 = client.post("/v1/fraud/evaluate", json={
        "tx_id": "bl_tx", "score": 0.0, "amount": 1000, "user_id": "bad_actor"
    })
    assert r3.json()["final_action"] == "BLOCK"
    assert "BLACKLIST" in (r3.json()["rule_id"] or "")

    # 제거
    r4 = client.request("DELETE", "/admin/api/blacklist", json={"kind": "user_id", "value": "bad_actor"})
    assert r4.status_code == 200


def test_whitelist_api_bypasses_rules():
    # 화이트리스트 추가
    client.post("/admin/api/whitelist", json={"user_id": "vip_customer"})

    # 높은 금액이어도 Rule Engine 통과 → model_action만 반영
    r = client.post("/v1/fraud/evaluate", json={
        "tx_id": "wl_tx", "score": 0.1, "amount": 9_000_000, "user_id": "vip_customer"
    })
    data = r.json()
    assert data["rule_action"] == "PASS"

    # 제거
    client.request("DELETE", "/admin/api/whitelist", json={"user_id": "vip_customer"})


def test_blacklist_invalid_kind():
    r = client.post("/admin/api/blacklist", json={"kind": "phone", "value": "010-1234"})
    assert r.status_code == 422


def test_health_detail():
    r = client.get("/health/detail")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "components" in data
    assert "model" in data["components"]
    assert "kafka" in data["components"]
