"""W10-#2 — 부하 테스트 스크립트 정합성 (네트워크 호출 없이 헬퍼 단위 테스트)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "loadtest" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("loadtest_run", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_script_imports():
    mod = _load()
    assert hasattr(mod, "run_loadtest")
    assert hasattr(mod, "_payload")


def test_payload_has_required_fields():
    mod = _load()
    p = mod._payload(0)
    for key in ("tx_id", "user_id", "amount", "type", "score"):
        assert key in p
    assert 10_000 <= p["amount"] <= 50_000_000


def test_payload_tx_id_prefix_valid():
    mod = _load()
    p = mod._payload(5)
    prefix = p["tx_id"].split("-")[0]
    assert prefix in {"VP", "MM", "ATO", "CT", "TX"}


def test_percentile_edge_cases():
    mod = _load()
    assert mod._percentile([], 99) == 0.0
    assert mod._percentile([10.0], 50) == 10.0
    assert mod._percentile([1, 2, 3, 4, 5], 50) == 3
    assert mod._percentile([1, 2, 3, 4, 5], 100) == 5
