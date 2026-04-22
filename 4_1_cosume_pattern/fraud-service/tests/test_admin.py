from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_admin_page():
    r = client.get("/admin")
    assert r.status_code == 200
    assert "관리" in r.text or "Fraud" in r.text


def test_admin_status_json():
    r = client.get("/admin/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "fraud-service"
    assert "model" in data
    assert "metrics" in data
