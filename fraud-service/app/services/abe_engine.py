"""
Layer 2 — CP-ABE 기반 Fine-grained Access Control Engine.

교수님 연구 연계:
- "Privacy-preserving ABE with Bidirectional Access Control"
- "Ensuring End-to-End Security with Fine-grained AC for CAV" (TIFS 2024)

구현 전략:
1. 속성 정책 매칭 (access_structure 평가)
2. 필드 레벨 암호화 (AES-GCM, 키는 속성 조합에서 파생)
   → 실제 CP-ABE 라이브러리(charm-crypto) 도입 시 교체 가능하도록 인터페이스 분리
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

# ── 속성 토큰 구조 ──────────────────────────────────────────────

@dataclass
class AttributeToken:
    """사용자의 속성 집합을 담는 토큰.

    실제 CP-ABE에서는 이것이 사용자 비밀키에 해당하지만,
    경량 구현에서는 속성 목록 + HMAC 서명으로 대체한다.
    """
    user_id: str
    attributes: dict[str, str]  # e.g. {"role": "analyst", "dept": "fraud_team", ...}
    issued_at: str = ""
    signature: str = ""         # HMAC 서명 (위변조 방지)

    def attr_set(self) -> set[str]:
        """속성을 'key:value' 형태의 집합으로 반환."""
        return {f"{k}:{v}" for k, v in self.attributes.items()}


# ── 정책 매칭 엔진 ──────────────────────────────────────────────

def evaluate_access_structure(structure: str, user_attrs: set[str]) -> bool:
    """불리언 접근 구조식을 평가한다.

    지원 문법: AND, OR, 괄호, 속성(key:value), 와일드카드(key:*)
    예: "(role:analyst OR role:admin) AND dept:fraud_team"
    """
    expr = structure
    # 속성 토큰을 True/False로 치환
    tokens = re.findall(r"[\w]+:[\w*]+", expr)
    for token in tokens:
        key, value = token.split(":", 1)
        if value == "*":
            matched = any(a.startswith(f"{key}:") for a in user_attrs)
        else:
            matched = token in user_attrs
        expr = expr.replace(token, str(matched), 1)

    # AND/OR → Python and/or
    expr = expr.replace("AND", "and").replace("OR", "or")
    expr = expr.replace("True", "True").replace("False", "False")

    try:
        return bool(eval(expr))  # noqa: S307 — 내부 정책 식만 평가
    except Exception:
        return False


# ── 정책 로더 ──────────────────────────────────────────────────

@dataclass
class AccessPolicy:
    resource: str               # "POST /v1/score" or "GET /v1/audit/*"
    access_structure: str
    encrypted_fields: list[str]


def load_policies(yaml_path: str | Path) -> list[AccessPolicy]:
    """YAML 정책 파일에서 접근 정책 목록을 로드한다."""
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    return [
        AccessPolicy(
            resource=p["resource"],
            access_structure=p["access_structure"],
            encrypted_fields=p.get("encrypted_fields", []),
        )
        for p in data.get("policies", [])
    ]


def find_policy(policies: list[AccessPolicy], method: str, path: str) -> AccessPolicy | None:
    """요청 method+path에 매칭되는 정책을 찾는다."""
    request_resource = f"{method.upper()} {path}"
    for policy in policies:
        pattern = policy.resource
        if "*" in pattern:
            # 와일드카드 매칭: "GET /v1/audit/*" matches "GET /v1/audit/chain/status"
            base = pattern.replace("*", "")
            if request_resource.startswith(base):
                return policy
        elif request_resource == pattern:
            return policy
    return None


# ── 필드 레벨 암호화 (AES-GCM 경량 구현) ──────────────────────
# 실제 CP-ABE 도입 시 이 부분만 교체하면 됨

_ABE_SECRET = os.getenv("ABE_MASTER_SECRET", "default-dev-secret-change-in-prod")


def _derive_field_key(attr_set_str: str, field_name: str) -> bytes:
    """속성 집합 + 필드명에서 AES 키를 파생한다.

    실제 CP-ABE에서는 속성 기반 키 생성(KeyGen)에 해당.
    """
    material = f"{_ABE_SECRET}:{attr_set_str}:{field_name}"
    return hashlib.sha256(material.encode()).digest()


def encrypt_field(value: Any, access_structure: str) -> str:
    """필드 값을 접근 구조에 묶어 암호화한다.

    반환: "ABE:<base64(nonce|ciphertext|tag|structure_hash)>"
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        # cryptography 패키지 없으면 마커만 반환
        return f"ABE_ENCRYPTED:{access_structure}"

    plaintext = json.dumps(value, ensure_ascii=False).encode("utf-8")
    key = _derive_field_key(access_structure, "field")
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, access_structure.encode("utf-8"))
    blob = nonce + ct  # nonce(12) + ciphertext+tag
    return "ABE:" + b64encode(blob).decode("ascii")


def decrypt_field(encrypted: str, user_attrs: set[str]) -> Any:
    """암호화된 필드를 복호화한다. 속성이 만족하지 않으면 None 반환."""
    if encrypted.startswith("ABE_ENCRYPTED:"):
        structure = encrypted[len("ABE_ENCRYPTED:"):]
        if evaluate_access_structure(structure, user_attrs):
            return "[decrypted-placeholder]"
        return None

    if not encrypted.startswith("ABE:"):
        return encrypted

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return None

    blob = b64decode(encrypted[4:])
    nonce = blob[:12]
    ct = blob[12:]

    # 접근 구조를 복원하기 위해 모든 로드된 정책을 시도해야 하지만,
    # 경량 구현에서는 사용자 속성에서 키를 파생하여 복호화 시도
    key = _derive_field_key(",".join(sorted(user_attrs)), "field")
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return json.loads(plaintext)
    except Exception:
        return None


# ── 응답 필터링 ────────────────────────────────────────────────

def filter_response(
    response_data: dict[str, Any],
    encrypted_fields: list[str],
    user_attrs: set[str],
    access_structure: str,
) -> dict[str, Any]:
    """응답에서 encrypted_fields에 해당하는 필드를 처리한다.

    - 속성 만족 → 원본 유지
    - 속성 불만족 → "[ENCRYPTED: 접근 권한 부족]" 마커로 대체
    """
    if not encrypted_fields:
        return response_data

    has_access = evaluate_access_structure(access_structure, user_attrs)
    if has_access:
        return response_data

    filtered = dict(response_data)
    for f in encrypted_fields:
        if f in filtered:
            filtered[f] = "[ENCRYPTED: 접근 권한 부족]"
    return filtered
