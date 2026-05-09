"""W9-#11 — MyData 동의 철회 소유권 검증 단위 테스트.

전체 라우터 import 시 ML/Sentry 부트스트랩이 필요해 로직만 직접 시뮬레이션.
"""
from __future__ import annotations


def _check_ownership(consent_user_id: str, current_user_id: str, is_admin: bool) -> bool:
    """라우터의 소유권 검증 로직 (실제 코드와 동일한 분기)."""
    if is_admin:
        return True
    return str(consent_user_id) == str(current_user_id)


def test_owner_can_revoke():
    assert _check_ownership("u1", "u1", is_admin=False) is True


def test_other_user_cannot_revoke():
    assert _check_ownership("u1", "u2", is_admin=False) is False


def test_admin_can_revoke_any():
    assert _check_ownership("u1", "u_admin", is_admin=True) is True


def test_int_id_coerces():
    assert _check_ownership(1, "1", is_admin=False) is True
    assert _check_ownership(1, "2", is_admin=False) is False
