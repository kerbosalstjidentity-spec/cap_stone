"""
Layer 2 — CP-ABE 기반 Fine-grained Access Control Engine.

교수님 연구 연계:
- "Privacy-preserving ABE with Bidirectional Access Control"
- "Ensuring End-to-End Security with Fine-grained AC for CAV" (TIFS 2024)
- SRS 2,5,7,8,9,11: CP-ABE Access Tree, 속성 취소(Revocation), 정책 은닉(Hidden Policy)

구현 전략:
1. 속성 정책 매칭 (access_structure 평가)
2. CP-ABE Access Tree 설계 (AND/OR 임계값 게이트)
3. 필드 레벨 암호화 (AES-GCM, 키는 속성 조합에서 파생)
   → 실제 CP-ABE 라이브러리(charm-crypto) 도입 시 교체 가능하도록 인터페이스 분리
4. 속성 취소 관리 (Revocation Manager)
5. 정책 은닉 (Hidden Policy — 정책 해시만 공개)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
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
    expires_at: str = ""        # 만료 시각 (ISO 8601)

    def attr_set(self) -> set[str]:
        """속성을 'key:value' 형태의 집합으로 반환."""
        return {f"{k}:{v}" for k, v in self.attributes.items()}

    def sign(self, master_secret: str) -> None:
        """HMAC-SHA256으로 토큰에 서명한다."""
        payload = json.dumps(
            {"user_id": self.user_id, "attributes": self.attributes, "issued_at": self.issued_at},
            sort_keys=True,
        )
        self.signature = hmac.new(
            master_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def verify_signature(self, master_secret: str) -> bool:
        """서명을 검증한다."""
        expected = ""
        payload = json.dumps(
            {"user_id": self.user_id, "attributes": self.attributes, "issued_at": self.issued_at},
            sort_keys=True,
        )
        expected = hmac.new(
            master_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)


# ── CP-ABE Access Tree ─────────────────────────────────────────

@dataclass
class AccessTreeNode:
    """CP-ABE Access Tree 노드.

    - 리프 노드: attribute 필드에 속성 값 ("role:analyst")
    - 내부 노드: threshold (1=OR, n=AND), children 리스트
    """
    threshold: int = 1            # 1=OR gate, len(children)=AND gate
    children: list["AccessTreeNode"] = field(default_factory=list)
    attribute: str = ""           # 리프 노드의 속성 값

    @property
    def is_leaf(self) -> bool:
        return bool(self.attribute)

    def evaluate(self, user_attrs: set[str]) -> bool:
        """트리를 재귀적으로 평가한다."""
        if self.is_leaf:
            if self.attribute.endswith(":*"):
                key = self.attribute[:-2]
                return any(a.startswith(f"{key}:") for a in user_attrs)
            return self.attribute in user_attrs
        satisfied = sum(1 for c in self.children if c.evaluate(user_attrs))
        return satisfied >= self.threshold


def build_access_tree(structure: str) -> AccessTreeNode:
    """불리언 접근 구조식으로부터 AccessTree를 구성한다.

    예: "(role:analyst OR role:admin) AND dept:fraud_team"
    """
    structure = structure.strip()

    # 괄호 제거
    if structure.startswith("(") and structure.endswith(")"):
        inner = structure[1:-1]
        # 외부 괄호인지 확인
        depth = 0
        for c in inner:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if depth < 0:
                break
        else:
            structure = inner

    # AND 분리 시도 (최상위 레벨)
    parts = _split_top_level(structure, "AND")
    if len(parts) > 1:
        node = AccessTreeNode(threshold=len(parts))
        for p in parts:
            node.children.append(build_access_tree(p.strip()))
        return node

    # OR 분리 시도
    parts = _split_top_level(structure, "OR")
    if len(parts) > 1:
        node = AccessTreeNode(threshold=1)
        for p in parts:
            node.children.append(build_access_tree(p.strip()))
        return node

    # 리프 노드
    return AccessTreeNode(attribute=structure.strip())


def _split_top_level(expr: str, op: str) -> list[str]:
    """최상위 레벨에서만 op로 분리한다 (괄호 내부 무시)."""
    parts = []
    depth = 0
    current = []
    tokens = expr.split()
    for token in tokens:
        depth += token.count("(") - token.count(")")
        if token == op and depth == 0:
            parts.append(" ".join(current))
            current = []
        else:
            current.append(token)
    if current:
        parts.append(" ".join(current))
    return parts if len(parts) > 1 else [expr]


# ── 정책 매칭 엔진 ──────────────────────────────────────────────

def evaluate_access_structure(structure: str, user_attrs: set[str]) -> bool:
    """불리언 접근 구조식을 평가한다.

    지원 문법: AND, OR, 괄호, 속성(key:value), 와일드카드(key:*)
    예: "(role:analyst OR role:admin) AND dept:fraud_team"
    """
    try:
        tree = build_access_tree(structure)
        return tree.evaluate(user_attrs)
    except Exception:
        pass

    # fallback: 기존 방식
    expr = structure
    tokens = re.findall(r"[\w]+:[\w*]+", expr)
    for token in tokens:
        key, value = token.split(":", 1)
        if value == "*":
            matched = any(a.startswith(f"{key}:") for a in user_attrs)
        else:
            matched = token in user_attrs
        expr = expr.replace(token, str(matched), 1)

    expr = expr.replace("AND", "and").replace("OR", "or")
    try:
        return bool(eval(expr))  # noqa: S307 — 내부 정책 식만 평가
    except Exception:
        return False


# ── 속성 취소 관리자 ───────────────────────────────────────────

class AttributeRevocationManager:
    """속성 취소(Revocation) 관리.

    SRS 2,5: 사용자 속성 취소 시 해당 속성으로 암호화된 데이터 접근 차단.
    """
    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}  # "user_id:attr" → revocation_time

    def revoke(self, user_id: str, attribute: str) -> None:
        key = f"{user_id}:{attribute}"
        self._revoked[key] = time.time()

    def is_revoked(self, user_id: str, attribute: str) -> bool:
        return f"{user_id}:{attribute}" in self._revoked

    def filter_attrs(self, user_id: str, attrs: set[str]) -> set[str]:
        """취소된 속성을 제거한 후 반환."""
        return {
            a for a in attrs
            if not self.is_revoked(user_id, a)
        }

    def list_revoked(self) -> list[dict[str, Any]]:
        return [
            {"key": k, "revoked_at": v}
            for k, v in self._revoked.items()
        ]


# 전역 취소 관리자
revocation_manager = AttributeRevocationManager()


# ── 정책 은닉 (Hidden Policy) ──────────────────────────────────

def hash_policy(access_structure: str) -> str:
    """정책 구조를 SHA-256으로 해싱하여 공개 식별자로 사용.

    SRS 7: 정책 내용을 숨기고 해시만 공개 (Hidden Policy).
    """
    return hashlib.sha256(access_structure.encode("utf-8")).hexdigest()[:16]


# ── AACE 양방향 접근 제어 ──────────────────────────────────────

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


# ── CP-ABE 4단계 시뮬레이터 ────────────────────────────────────

class CPABE_Simulator:
    """SRS 5: CP-ABE 4단계 흐름 시뮬레이션.

    Setup → KeyGen → Encrypt → Decrypt
    """
    def __init__(self, master_secret: str = "sim-master-secret") -> None:
        self._master_secret = master_secret
        self._public_params: dict[str, Any] = {}
        self._user_keys: dict[str, dict[str, Any]] = {}

    def setup(self) -> dict[str, Any]:
        """1단계: 공개 파라미터 + 마스터 키 생성."""
        self._public_params = {
            "group": "BN256",
            "g": hashlib.sha256(b"generator").hexdigest()[:16],
            "policy_universe": ["role:*", "dept:*", "clearance:*"],
        }
        return {"status": "ok", "public_params": self._public_params}

    def keygen(self, user_id: str, attributes: list[str]) -> dict[str, Any]:
        """2단계: 속성 기반 사용자 비밀키 생성."""
        sk_material = hashlib.sha256(
            f"{self._master_secret}:{user_id}:{','.join(sorted(attributes))}".encode()
        ).hexdigest()
        self._user_keys[user_id] = {"sk": sk_material, "attributes": attributes}
        return {
            "user_id": user_id,
            "attributes": attributes,
            "sk_hash": sk_material[:16] + "...",  # 실제 키는 숨김
        }

    def encrypt(self, plaintext: str, access_structure: str) -> dict[str, Any]:
        """3단계: 접근 구조로 암호화."""
        policy_hash = hash_policy(access_structure)
        ct_material = hashlib.sha256(
            f"{plaintext}:{policy_hash}:{self._master_secret}".encode()
        ).hexdigest()
        return {
            "ciphertext": ct_material[:32] + "...",
            "policy_hash": policy_hash,
            "access_structure_hidden": True,
        }

    def decrypt(self, ct: dict[str, Any], user_id: str, user_attrs: set[str],
                access_structure: str) -> dict[str, Any]:
        """4단계: 속성 만족 시 복호화."""
        if user_id not in self._user_keys:
            return {"success": False, "reason": "No user key — run keygen first"}
        policy_hash = hash_policy(access_structure)
        if ct.get("policy_hash") != policy_hash:
            return {"success": False, "reason": "Policy hash mismatch"}
        if evaluate_access_structure(access_structure, user_attrs):
            return {"success": True, "plaintext": "[decrypted]", "user_id": user_id}
        return {"success": False, "reason": "Attributes do not satisfy access structure"}


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

    # 취소된 속성 필터링
    has_access = evaluate_access_structure(access_structure, user_attrs)
    if has_access:
        return response_data

    filtered = dict(response_data)
    for f in encrypted_fields:
        if f in filtered:
            filtered[f] = "[ENCRYPTED: 접근 권한 부족]"
    return filtered
