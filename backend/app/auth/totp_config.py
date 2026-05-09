"""TOTP 운영 파라미터 (W9-#12).

routes_auth / routes_stepup 양쪽이 공유하는 작은 유틸 — 외부 의존 없음.
"""
from __future__ import annotations

import os


def totp_valid_window() -> int:
    """TOTP_VALID_WINDOW env. 기본 1(±30s), 최대 5 까지 허용."""
    raw = os.getenv("TOTP_VALID_WINDOW", "1")
    try:
        return max(0, min(int(raw), 5))
    except ValueError:
        return 1
