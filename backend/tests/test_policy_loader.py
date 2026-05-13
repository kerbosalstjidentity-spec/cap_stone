"""W8-#3 — 정책 핫 리로드 테스트."""
from __future__ import annotations

import json
import os
import time

from app.services.policy_loader import (
    PolicyFile,
    list_policies,
    register_policy,
    reload_all,
)


def test_initial_load(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    pol = PolicyFile(p)
    assert pol.get() == {"x": 1}


def test_missing_file_returns_default(tmp_path):
    pol = PolicyFile(tmp_path / "nope.json")
    assert pol.get(default={"fallback": True}) == {"fallback": True}
    assert "없음" in pol.last_error


def test_hot_reload_on_mtime_change(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"v": 1}), encoding="utf-8")
    pol = PolicyFile(p)
    assert pol.get()["v"] == 1

    time.sleep(1.1)  # mtime 1초 단위 보장
    p.write_text(json.dumps({"v": 2}), encoding="utf-8")
    # mtime 명시적 갱신
    os.utime(p, None)
    assert pol.get()["v"] == 2


def test_force_reload(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"k": "a"}), encoding="utf-8")
    pol = PolicyFile(p)
    out = pol.force_reload()
    assert out["loaded"] is True
    assert pol.get()["k"] == "a"


def test_invalid_json_keeps_cache(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"v": 1}), encoding="utf-8")
    pol = PolicyFile(p)
    assert pol.get()["v"] == 1
    # 깨진 JSON 으로 덮어쓰기
    time.sleep(1.1)
    p.write_text("{invalid", encoding="utf-8")
    os.utime(p, None)
    out = pol.force_reload()
    assert out["loaded"] is False
    assert out["error"] is not None


def test_registry_reload_all(tmp_path):
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps({"a": 1}), encoding="utf-8")
    p2 = tmp_path / "b.json"
    p2.write_text(json.dumps({"b": 2}), encoding="utf-8")
    register_policy("test_a", p1)
    register_policy("test_b", p2)
    out = reload_all()
    assert out["test_a"]["loaded"] is True
    assert out["test_b"]["loaded"] is True
    listing = list_policies()
    assert "test_a" in listing
    assert listing["test_b"]["exists"] is True
