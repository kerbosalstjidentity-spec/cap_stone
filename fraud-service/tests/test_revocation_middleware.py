"""W8-#8 — revocation_manager.filter_attrs() 미들웨어 적용 테스트."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.abe_auth import _filter_revoked_attrs
from app.services.abe_engine import revocation_manager

client = TestClient(app)


def setup_function(_):
    revocation_manager._revoked.clear()


def teardown_function(_):
    revocation_manager._revoked.clear()


def test_no_revocation_returns_attrs_as_is():
    attrs = {"role": "admin", "dept": "fraud"}
    assert _filter_revoked_attrs("u1", attrs) == attrs


def test_revoked_attr_removed():
    revocation_manager.revoke("u1", "role:admin")
    attrs = {"role": "admin", "dept": "fraud"}
    out = _filter_revoked_attrs("u1", attrs)
    assert "role" not in out
    assert out["dept"] == "fraud"


def test_revocation_scoped_to_user():
    revocation_manager.revoke("u1", "role:admin")
    attrs = {"role": "admin"}
    # 다른 사용자는 영향 없음
    assert _filter_revoked_attrs("u2", attrs) == attrs


def test_admin_revoke_endpoint():
    r = client.post(
        "/admin/api/revocations",
        json={"user_id": "u9", "attribute": "role:admin"},
    )
    assert r.status_code == 201
    assert r.json()["revoked"] is True
    # 목록 조회
    r2 = client.get("/admin/api/revocations")
    assert r2.status_code == 200
    keys = [item["key"] for item in r2.json()["revoked"]]
    assert "u9:role:admin" in keys


def test_admin_revoke_missing_field_422():
    r = client.post("/admin/api/revocations", json={"user_id": "u9"})
    assert r.status_code == 422
