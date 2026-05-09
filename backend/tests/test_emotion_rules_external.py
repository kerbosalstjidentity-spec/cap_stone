"""W5-#8: 감정 룰 JSON 외부화 — 헬퍼만 단위 테스트 (라우터 import 회피)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def test_default_rules_load():
    from app.services import emotion_engine
    rules = emotion_engine._load_emotion_rules()
    assert "hour_risk" in rules
    assert "risk_bands" in rules
    assert rules["weekend_bonus"] == 0.1


def test_hour_risk_built_from_rules():
    from app.services import emotion_engine
    rules = emotion_engine._load_emotion_rules()
    hr = emotion_engine._build_hour_risk(rules)
    # 기본 정책: 22시는 night band 0.4, 13시는 midday 0.1
    assert hr.get(22) == 0.4
    assert hr.get(13) == 0.1


def test_missing_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("EMOTION_RULES_PATH", str(tmp_path / "missing.json"))
    from app.services import emotion_engine
    rules = emotion_engine._load_emotion_rules()
    assert rules == {}
    # _build_hour_risk 는 빈 dict 면 기본값으로 폴백
    hr = emotion_engine._build_hour_risk({})
    assert hr.get(22) == 0.4
    assert hr.get(13) == 0.1


def test_reload_picks_up_override(tmp_path, monkeypatch):
    custom = {
        "hour_risk": {"all": {"hours": list(range(24)), "weight": 0.5}},
        "weekend_bonus": 0.25,
        "risk_bands": {"safe": {"min_score": 0.0, "message": "ok"}},
    }
    p = tmp_path / "custom.json"
    p.write_text(json.dumps(custom), encoding="utf-8")
    monkeypatch.setenv("EMOTION_RULES_PATH", str(p))

    from app.services import emotion_engine
    emotion_engine.reload_emotion_rules()
    assert emotion_engine.WEEKEND_BONUS == 0.25
    assert emotion_engine.HOUR_RISK[10] == 0.5

    # 원복
    monkeypatch.delenv("EMOTION_RULES_PATH")
    emotion_engine.reload_emotion_rules()
    assert emotion_engine.WEEKEND_BONUS == 0.1
