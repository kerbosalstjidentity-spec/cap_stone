"""ABAC/CP-ABE 시뮬레이션 — 운영 평가 경로 외 학술 데모용.

W9-#13: ``app.services.abe_engine`` 에서 분리. 운영 룰 엔진/스코어 경로
는 ``evaluate_access_structure`` (단순 boolean 평가) 만 사용하고, 본 모듈
의 ``BidirectionalPolicy`` (No-read+No-write) 와 ``CPABE_Simulator`` (4단계
흐름) 는 SRS 발표·논문 데모용.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.abe_engine import evaluate_access_structure, hash_policy


@dataclass
class BidirectionalPolicy:
    """SRS 2: No-read + No-write 동시 적용 정책.

    - no_read_structure: 이 조건 만족 시 읽기 차단
    - no_write_structure: 이 조건 만족 시 쓰기 차단
    """
    resource: str
    no_read_structure: str = ""
    no_write_structure: str = ""
    normal_access_structure: str = ""

    def can_read(self, user_attrs: set[str]) -> bool:
        if self.no_read_structure and evaluate_access_structure(self.no_read_structure, user_attrs):
            return False
        if self.normal_access_structure:
            return evaluate_access_structure(self.normal_access_structure, user_attrs)
        return True

    def can_write(self, user_attrs: set[str]) -> bool:
        if self.no_write_structure and evaluate_access_structure(self.no_write_structure, user_attrs):
            return False
        if self.normal_access_structure:
            return evaluate_access_structure(self.normal_access_structure, user_attrs)
        return True


class CPABE_Simulator:
    """SRS 5: CP-ABE 4단계 흐름 시뮬레이션.

    Setup → KeyGen → Encrypt → Decrypt
    """

    def __init__(self, master_secret: str = "sim-master-secret") -> None:
        self._master_secret = master_secret
        self._public_params: dict[str, Any] = {}
        self._user_keys: dict[str, dict[str, Any]] = {}

    def setup(self) -> dict[str, Any]:
        self._public_params = {
            "group": "BN256",
            "g": hashlib.sha256(b"generator").hexdigest()[:16],
            "policy_universe": ["role:*", "dept:*", "clearance:*"],
        }
        return {"status": "ok", "public_params": self._public_params}

    def keygen(self, user_id: str, attributes: list[str]) -> dict[str, Any]:
        sk_material = hashlib.sha256(
            f"{self._master_secret}:{user_id}:{','.join(sorted(attributes))}".encode()
        ).hexdigest()
        self._user_keys[user_id] = {"sk": sk_material, "attributes": attributes}
        return {
            "user_id": user_id,
            "attributes": attributes,
            "sk_hash": sk_material[:16] + "...",
        }

    def encrypt(self, plaintext: str, access_structure: str) -> dict[str, Any]:
        policy_hash = hash_policy(access_structure)
        ct_material = hashlib.sha256(
            f"{plaintext}:{policy_hash}:{self._master_secret}".encode()
        ).hexdigest()
        return {
            "ciphertext": ct_material[:32] + "...",
            "policy_hash": policy_hash,
            "access_structure_hidden": True,
        }

    def decrypt(
        self,
        ct: dict[str, Any],
        user_id: str,
        user_attrs: set[str],
        access_structure: str,
    ) -> dict[str, Any]:
        if user_id not in self._user_keys:
            return {"success": False, "reason": "No user key — run keygen first"}
        policy_hash = hash_policy(access_structure)
        if ct.get("policy_hash") != policy_hash:
            return {"success": False, "reason": "Policy hash mismatch"}
        if evaluate_access_structure(access_structure, user_attrs):
            return {"success": True, "plaintext": "[decrypted]", "user_id": user_id}
        return {"success": False, "reason": "Attributes do not satisfy access structure"}
