"""W8-#7 — KPI ↔ ML 매핑 문서 정합성 테스트."""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "kpi_ml_mapping.md"


def _body() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists():
    assert DOC.is_file()


def test_mapping_references_w7_endpoints():
    body = _body()
    assert "/admin/api/ab-precision-recall" in body
    assert "/admin/api/drift" in body
    assert "/admin/api/score-distribution" in body
    assert "/admin/api/latency" in body
    assert "/admin/api/slo" in body


def test_mapping_references_w8_modules():
    body = _body()
    assert "fp_cost_analyzer" in body
    assert "alarm_manager" in body


def test_loss_formula_present():
    body = _body()
    assert "expected_loss" in body
    assert "recall" in body
    assert "FPR" in body
