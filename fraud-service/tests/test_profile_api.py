"""Profile API 테스트."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
USER = "test_user_api"


def test_ingest_and_get():
    client.post("/v1/profile/ingest", json={
        "user_id": USER, "tx_id": "t1", "amount": 50_000,
        "merchant_id": "m1", "hour": 14,
    })
    r = client.get(f"/v1/profile/{USER}")
    assert r.status_code == 200
    data = r.json()
    assert data["tx_count"] >= 1
    assert data["avg_amount"] == 50_000


def test_get_unknown_user():
    r = client.get("/v1/profile/nobody_xyz")
    assert r.status_code == 404


def test_velocity_endpoint():
    r = client.get(f"/v1/profile/{USER}/velocity")
    assert r.status_code == 200
    v = r.json()["velocity"]
    assert "1m" in v and "5m" in v and "15m" in v


def test_delete_profile():
    client.post("/v1/profile/ingest", json={
        "user_id": "del_user", "tx_id": "d1", "amount": 1000,
    })
    r = client.delete("/v1/profile/del_user")
    assert r.status_code == 204
    assert client.get("/v1/profile/del_user").status_code == 404


def test_delete_unknown():
    r = client.delete("/v1/profile/nobody_xyz_del")
    assert r.status_code == 404
