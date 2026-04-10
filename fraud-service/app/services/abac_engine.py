"""
Layer 2+ — ABAC (Attribute-Based Access Control) 세분화 접근 제어 엔진.

SRS 3 FR-02, FR-03 요구사항:
- 속성 기반 접근 결정 (직급 + 위치 + 시간 + 기기유형)
- 행(Row) / 열(Column) / 셀(Cell) 단위 데이터 마스킹
- FGAC vs CGAC 비교 시뮬레이션 지원 (SRS 3 SC-01)

교수님 연구 연계:
- "Fine-Grained Access Control for Financial Data on MEC"
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── 속성 컨텍스트 ──────────────────────────────────────────────

class ClearanceLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    TOP_SECRET = 4


@dataclass
class SubjectAttributes:
    """요청 주체(사용자)의 속성."""
    user_id: str
    role: str                           # analyst, admin, auditor, viewer
    department: str                     # fraud_team, compliance, operations
    clearance: ClearanceLevel = ClearanceLevel.LOW
    position: str = ""                  # 직급: junior, senior, manager, director
    location: str = ""                  # 접속 위치: internal, vpn, external
    device_type: str = ""               # desktop, mobile, tablet
    mfa_verified: bool = False
    ip_country: str = "KR"


@dataclass
class ResourceAttributes:
    """접근 대상 리소스의 속성."""
    resource_type: str                  # transaction, profile, audit_log, report
    sensitivity: ClearanceLevel = ClearanceLevel.LOW
    owner_department: str = ""
    data_classification: str = "internal"  # public, internal, confidential, restricted


@dataclass
class EnvironmentAttributes:
    """환경 컨텍스트."""
    current_hour: int = -1              # 0~23, -1이면 현재 시간 사용
    is_business_hours: bool = True
    threat_level: str = "normal"        # normal, elevated, high, critical
    request_timestamp: float = 0.0

    def __post_init__(self):
        if self.current_hour == -1:
            self.current_hour = datetime.now(tz=timezone.utc).hour
        if self.request_timestamp == 0.0:
            self.request_timestamp = time.time()
        self.is_business_hours = 9 <= self.current_hour < 18


# ── ABAC 접근 결정 ─────────────────────────────────────────────

@dataclass
class AccessDecision:
    """ABAC 접근 결정 결과."""
    allowed: bool
    reason: str
    masked_fields: list[str] = field(default_factory=list)
    masked_rows: list[int] = field(default_factory=list)
    masking_level: str = "none"         # none, column, row, cell
    applied_rules: list[str] = field(default_factory=list)


class ABACEngine:
    """속성 기반 접근 제어 엔진.

    SRS 3 요구사항에 따라 다차원 속성을 평가하여
    행/열/셀 단위 접근 결정을 내린다.
    """

    def __init__(self) -> None:
        self._rules: list[ABACRule] = self._default_rules()

    def evaluate(
        self,
        subject: SubjectAttributes,
        resource: ResourceAttributes,
        env: EnvironmentAttributes | None = None,
    ) -> AccessDecision:
        """모든 ABAC 규칙을 평가하여 접근 결정을 반환."""
        if env is None:
            env = EnvironmentAttributes()

        applied_rules: list[str] = []
        denied_reason = ""
        masked_fields: list[str] = []
        masking_level = "none"

        for rule in self._rules:
            result = rule.evaluate(subject, resource, env)
            if result is not None:
                applied_rules.append(rule.rule_id)
                if result["action"] == "DENY":
                    denied_reason = result["reason"]
                    break
                elif result["action"] == "MASK_COLUMN":
                    masked_fields.extend(result.get("fields", []))
                    masking_level = "column"
                elif result["action"] == "MASK_ROW":
                    masking_level = "row"
                    masked_fields.extend(result.get("fields", []))
                elif result["action"] == "MASK_CELL":
                    if masking_level != "row":
                        masking_level = "cell"
                    masked_fields.extend(result.get("fields", []))

        if denied_reason:
            return AccessDecision(
                allowed=False, reason=denied_reason,
                applied_rules=applied_rules,
            )

        return AccessDecision(
            allowed=True, reason="접근 허용",
            masked_fields=list(set(masked_fields)),
            masking_level=masking_level,
            applied_rules=applied_rules,
        )

    def mask_data(
        self,
        data: list[dict[str, Any]],
        decision: AccessDecision,
        sensitive_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """접근 결정에 따라 데이터를 마스킹한다.

        SRS 3 FR-03: 행/열/셀 단위 마스킹
        """
        if not decision.allowed:
            return []

        if decision.masking_level == "none":
            return data

        masked = []
        fields_to_mask = decision.masked_fields or sensitive_columns or []

        for i, row in enumerate(data):
            if decision.masking_level == "row":
                if decision.masked_rows and i in decision.masked_rows:
                    # 특정 행만 전체 마스킹
                    masked.append({k: "***" for k in row})
                elif not decision.masked_rows:
                    # masked_rows 미지정 시 모든 행에 필드 마스킹
                    new_row = {}
                    for k, v in row.items():
                        new_row[k] = _mask_value(v) if k in fields_to_mask else v
                    masked.append(new_row)
                else:
                    masked.append(dict(row))
            else:
                new_row = {}
                for k, v in row.items():
                    if k in fields_to_mask:
                        new_row[k] = _mask_value(v)
                    else:
                        new_row[k] = v
                masked.append(new_row)
        return masked

    def _default_rules(self) -> list[ABACRule]:
        return [
            ClearanceLevelRule(),
            BusinessHoursRule(),
            LocationRestrictionRule(),
            DeviceTypeRule(),
            MFARequirementRule(),
            DepartmentSeparationRule(),
            ThreatLevelRule(),
            SensitiveFieldMaskRule(),
        ]


# ── ABAC 규칙 인터페이스 ──────────────────────────────────────

class ABACRule:
    rule_id: str = ""

    def evaluate(
        self, subject: SubjectAttributes,
        resource: ResourceAttributes,
        env: EnvironmentAttributes,
    ) -> dict[str, Any] | None:
        raise NotImplementedError


# ── 구체 규칙들 ───────────────────────────────────────────────

class ClearanceLevelRule(ABACRule):
    """사용자 보안 등급 < 리소스 민감도 → 접근 거부."""
    rule_id = "CLEARANCE_LEVEL"

    def evaluate(self, subject, resource, env):
        if subject.clearance.value < resource.sensitivity.value:
            return {
                "action": "DENY",
                "reason": f"보안 등급 부족: {subject.clearance.name} < {resource.sensitivity.name}",
            }
        return None


class BusinessHoursRule(ABACRule):
    """업무 시간 외 + 기밀 리소스 접근 시 등급별 차등 제어.

    CRITICAL 민감도 → DENY (admin 제외)
    HIGH 민감도 → MASK_COLUMN
    """
    rule_id = "BUSINESS_HOURS"

    def evaluate(self, subject, resource, env):
        if not env.is_business_hours and resource.sensitivity.value >= ClearanceLevel.HIGH.value:
            if subject.role == "admin":
                return None  # 관리자는 예외
            if resource.sensitivity.value >= ClearanceLevel.CRITICAL.value:
                return {
                    "action": "DENY",
                    "reason": "업무 시간 외 CRITICAL 데이터 접근 거부",
                }
            return {
                "action": "MASK_COLUMN",
                "reason": "업무 시간 외 기밀 데이터 접근 — 민감 필드 마스킹",
                "fields": ["amount", "user_id", "score", "account_number"],
            }
        return None


class LocationRestrictionRule(ABACRule):
    """외부 접속 + 기밀 데이터 → 거부 또는 마스킹."""
    rule_id = "LOCATION_RESTRICTION"

    def evaluate(self, subject, resource, env):
        if subject.location == "external":
            if resource.sensitivity.value >= ClearanceLevel.TOP_SECRET.value:
                return {"action": "DENY", "reason": "외부 접속으로 최고기밀 데이터 접근 불가"}
            if resource.sensitivity.value >= ClearanceLevel.HIGH.value:
                return {
                    "action": "MASK_COLUMN",
                    "reason": "외부 접속 — 고기밀 필드 마스킹",
                    "fields": ["user_id", "account_number", "phone", "email"],
                }
        return None


class DeviceTypeRule(ABACRule):
    """모바일 기기에서 기밀 데이터 접근 시 마스킹."""
    rule_id = "DEVICE_TYPE"

    def evaluate(self, subject, resource, env):
        if subject.device_type in ("mobile", "tablet"):
            if resource.sensitivity.value >= ClearanceLevel.HIGH.value:
                return {
                    "action": "MASK_CELL",
                    "reason": "모바일 기기 — 민감 셀 마스킹",
                    "fields": ["amount", "score"],
                }
        return None


class MFARequirementRule(ABACRule):
    """MFA 미인증 + 민감 리소스 → 거부."""
    rule_id = "MFA_REQUIREMENT"

    def evaluate(self, subject, resource, env):
        if not subject.mfa_verified and resource.sensitivity.value >= ClearanceLevel.HIGH.value:
            return {"action": "DENY", "reason": "MFA 인증 필요: 고기밀 리소스 접근"}
        return None


class DepartmentSeparationRule(ABACRule):
    """직무 분리: 다른 부서의 기밀 리소스 접근 시 열 마스킹."""
    rule_id = "DEPT_SEPARATION"

    def evaluate(self, subject, resource, env):
        if (resource.owner_department
                and subject.department != resource.owner_department
                and subject.role != "admin"):
            if resource.sensitivity.value >= ClearanceLevel.MEDIUM.value:
                return {
                    "action": "MASK_COLUMN",
                    "reason": f"직무 분리: {subject.department} ≠ {resource.owner_department}",
                    "fields": ["user_id", "account_number", "phone", "score"],
                }
        return None


class ThreatLevelRule(ABACRule):
    """위협 레벨 high/critical 시 비관리자 접근 제한."""
    rule_id = "THREAT_LEVEL"

    def evaluate(self, subject, resource, env):
        if env.threat_level in ("high", "critical") and subject.role not in ("admin", "auditor"):
            if resource.sensitivity.value >= ClearanceLevel.MEDIUM.value:
                return {
                    "action": "MASK_COLUMN",
                    "reason": f"위협 레벨 {env.threat_level} — 민감 필드 마스킹",
                    "fields": ["amount", "user_id", "score", "rule_ids"],
                }
        return None


class SensitiveFieldMaskRule(ABACRule):
    """viewer 역할은 항상 PII 필드 마스킹."""
    rule_id = "SENSITIVE_FIELD_MASK"

    def evaluate(self, subject, resource, env):
        if subject.role == "viewer":
            return {
                "action": "MASK_COLUMN",
                "reason": "viewer 역할 — PII 마스킹",
                "fields": ["user_id", "account_number", "phone", "email", "ip"],
            }
        return None


# ── 유틸리티 ──────────────────────────────────────────────────

def _mask_value(value: Any) -> str:
    """값을 마스킹한다."""
    if value is None:
        return "***"
    s = str(value)
    if len(s) <= 2:
        return "***"
    return s[0] + "*" * (len(s) - 2) + s[-1]


# ── FGAC vs CGAC 비교 유틸 (SRS 3 SC-01) ─────────────────────

def simulate_cgac(role: str, resource_type: str) -> AccessDecision:
    """CGAC (Coarse-Grained Access Control) 시뮬레이션.

    역할만으로 전체 리소스 접근 여부를 결정하는 단순 모델.
    FGAC와의 비교 분석용.
    """
    role_permissions = {
        "admin": ["transaction", "profile", "audit_log", "report"],
        "analyst": ["transaction", "profile", "report"],
        "auditor": ["audit_log", "report"],
        "viewer": ["report"],
    }
    allowed_resources = role_permissions.get(role, [])
    if resource_type in allowed_resources:
        return AccessDecision(
            allowed=True, reason=f"CGAC: {role} → {resource_type} 허용",
            masking_level="none", applied_rules=["CGAC_ROLE_CHECK"],
        )
    return AccessDecision(
        allowed=False, reason=f"CGAC: {role} → {resource_type} 거부",
        applied_rules=["CGAC_ROLE_CHECK"],
    )


def compare_fgac_vs_cgac(
    subject: SubjectAttributes,
    resource: ResourceAttributes,
    env: EnvironmentAttributes | None = None,
) -> dict[str, Any]:
    """FGAC vs CGAC 비교 결과 반환."""
    engine = ABACEngine()
    fgac_result = engine.evaluate(subject, resource, env)
    cgac_result = simulate_cgac(subject.role, resource.resource_type)

    return {
        "fgac": {
            "allowed": fgac_result.allowed,
            "reason": fgac_result.reason,
            "masking_level": fgac_result.masking_level,
            "masked_fields": fgac_result.masked_fields,
            "rules_applied": len(fgac_result.applied_rules),
        },
        "cgac": {
            "allowed": cgac_result.allowed,
            "reason": cgac_result.reason,
            "masking_level": cgac_result.masking_level,
            "rules_applied": 1,
        },
        "comparison": {
            "fgac_more_restrictive": (
                not fgac_result.allowed and cgac_result.allowed
            ) or (
                fgac_result.masking_level != "none" and cgac_result.masking_level == "none"
            ),
            "granularity_difference": fgac_result.masking_level != cgac_result.masking_level,
        },
    }


# 싱글턴
abac_engine = ABACEngine()
