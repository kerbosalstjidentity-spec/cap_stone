"""policy_merge 최소 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fds"))

from policy_merge import decide_from_score, merge_actions  # noqa: E402


def test_merge_escalation() -> None:
    assert merge_actions("PASS", "BLOCK") == "BLOCK"
    assert merge_actions("REVIEW", "PASS") == "REVIEW"
    assert merge_actions("BLOCK", "REVIEW") == "BLOCK"


def test_decide_bands() -> None:
    assert decide_from_score(0.1, 0.95, 0.35) == "PASS"
    assert decide_from_score(0.4, 0.95, 0.35) == "REVIEW"
    assert decide_from_score(0.96, 0.95, 0.35) == "BLOCK"
