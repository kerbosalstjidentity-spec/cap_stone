"""W8-#1 — ABAC 단일 진실 출처 (policies/abac_unified.json) 정합성 테스트."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "policies" / "abac_unified.json"


def _load() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_policy_file_exists():
    assert POLICY.is_file()


def test_required_top_level_keys():
    data = _load()
    for key in ("version", "rules", "merge_strategy", "canonical_owner"):
        assert key in data, f"필수 키 누락: {key}"


def test_fraud_8_rules_complete():
    data = _load()
    fraud_rules = set(data["merge_strategy"]["fraud_8_rules"])
    assert len(fraud_rules) == 8
    # 모든 fraud 룰이 rules 정의에 존재
    defined = set(data["rules"].keys())
    assert fraud_rules.issubset(defined)


def test_backend_5_rules_subset_of_fraud():
    data = _load()
    backend = set(data["merge_strategy"]["backend_5_rules"])
    fraud = set(data["merge_strategy"]["fraud_8_rules"])
    assert backend.issubset(fraud), "backend 룰이 fraud 룰의 부분집합 아님"
    assert len(backend) == 5


def test_clearance_match_order_valid():
    data = _load()
    order = data["rules"]["clearance_match"]["order"]
    assert order == ["low", "medium", "high", "top_secret"]


def test_data_masking_fields_defined():
    data = _load()
    fields = data["rules"]["data_masking"]["fields"]
    assert "account_number" in fields
    assert "card_number" in fields
