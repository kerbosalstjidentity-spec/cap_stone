"""Tests for Layer 2: CP-ABE Access Control Engine."""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.abe_engine import (
    AccessPolicy,
    AttributeToken,
    evaluate_access_structure,
    filter_response,
    find_policy,
    load_policies,
)


class TestEvaluateAccessStructure:
    def test_simple_and(self):
        attrs = {"role:analyst", "dept:fraud_team"}
        assert evaluate_access_structure("role:analyst AND dept:fraud_team", attrs) is True

    def test_simple_and_fail(self):
        attrs = {"role:viewer", "dept:fraud_team"}
        assert evaluate_access_structure("role:analyst AND dept:fraud_team", attrs) is False

    def test_or(self):
        attrs = {"role:auditor"}
        assert evaluate_access_structure("role:auditor OR role:admin", attrs) is True

    def test_nested_parens(self):
        attrs = {"role:analyst", "dept:fraud_team"}
        assert evaluate_access_structure(
            "(role:analyst OR role:admin) AND dept:fraud_team", attrs
        ) is True

    def test_nested_fail(self):
        attrs = {"role:viewer", "dept:fraud_team"}
        assert evaluate_access_structure(
            "(role:analyst OR role:admin) AND dept:fraud_team", attrs
        ) is False

    def test_wildcard(self):
        attrs = {"institution:bank_a", "role:analyst"}
        assert evaluate_access_structure("institution:* AND role:analyst", attrs) is True

    def test_wildcard_no_match(self):
        attrs = {"role:analyst"}
        assert evaluate_access_structure("institution:* AND role:analyst", attrs) is False

    def test_complex_structure(self):
        attrs = {"role:admin", "clearance:high", "dept:fraud_team"}
        structure = "role:admin AND clearance:high"
        assert evaluate_access_structure(structure, attrs) is True


class TestFindPolicy:
    policies = [
        AccessPolicy("POST /v1/score", "(role:analyst OR role:admin) AND dept:fraud_team", ["reason_code"]),
        AccessPolicy("GET /v1/audit/*", "role:auditor OR role:admin", []),
        AccessPolicy("POST /v1/fraud/evaluate", "role:admin AND clearance:high", ["score"]),
    ]

    def test_exact_match(self):
        p = find_policy(self.policies, "POST", "/v1/score")
        assert p is not None
        assert p.resource == "POST /v1/score"

    def test_wildcard_match(self):
        p = find_policy(self.policies, "GET", "/v1/audit/chain/status")
        assert p is not None
        assert p.resource == "GET /v1/audit/*"

    def test_no_match(self):
        p = find_policy(self.policies, "GET", "/health")
        assert p is None


class TestFilterResponse:
    def test_access_granted(self):
        data = {"tx_id": "TX1", "score": 0.95, "reason_code": "V14"}
        result = filter_response(
            data,
            encrypted_fields=["score", "reason_code"],
            user_attrs={"role:admin", "clearance:high"},
            access_structure="role:admin AND clearance:high",
        )
        assert result["score"] == 0.95
        assert result["reason_code"] == "V14"

    def test_access_denied(self):
        data = {"tx_id": "TX1", "score": 0.95, "reason_code": "V14"}
        result = filter_response(
            data,
            encrypted_fields=["score", "reason_code"],
            user_attrs={"role:viewer"},
            access_structure="role:admin AND clearance:high",
        )
        assert result["tx_id"] == "TX1"  # 비암호화 필드는 유지
        assert "[ENCRYPTED" in result["score"]
        assert "[ENCRYPTED" in result["reason_code"]

    def test_no_encrypted_fields(self):
        data = {"status": "ok"}
        result = filter_response(data, [], {"role:viewer"}, "role:admin")
        assert result == data


class TestAttributeToken:
    def test_attr_set(self):
        token = AttributeToken(
            user_id="u1",
            attributes={"role": "analyst", "dept": "fraud_team", "clearance": "medium"},
        )
        expected = {"role:analyst", "dept:fraud_team", "clearance:medium"}
        assert token.attr_set() == expected


class TestLoadPolicies:
    def test_load_yaml(self):
        yaml_content = """
attributes:
  roles: [analyst, admin]
policies:
  - resource: "POST /v1/score"
    access_structure: "role:analyst OR role:admin"
    encrypted_fields: [reason_code]
  - resource: "GET /v1/audit/*"
    access_structure: "role:auditor"
    encrypted_fields: []
"""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            policies = load_policies(f.name)

        assert len(policies) == 2
        assert policies[0].resource == "POST /v1/score"
        assert "reason_code" in policies[0].encrypted_fields
        Path(f.name).unlink()
