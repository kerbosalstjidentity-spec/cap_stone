"""W9-#12 — TOTP valid_window env 노출 단위 테스트."""
from __future__ import annotations

import os

from app.auth.totp_config import totp_valid_window


def test_default_window():
    os.environ.pop("TOTP_VALID_WINDOW", None)
    assert totp_valid_window() == 1


def test_env_override():
    os.environ["TOTP_VALID_WINDOW"] = "2"
    try:
        assert totp_valid_window() == 2
    finally:
        os.environ.pop("TOTP_VALID_WINDOW", None)


def test_invalid_falls_back():
    os.environ["TOTP_VALID_WINDOW"] = "abc"
    try:
        assert totp_valid_window() == 1
    finally:
        os.environ.pop("TOTP_VALID_WINDOW", None)


def test_clipped_at_safe_max():
    os.environ["TOTP_VALID_WINDOW"] = "999"
    try:
        assert totp_valid_window() == 5
    finally:
        os.environ.pop("TOTP_VALID_WINDOW", None)


def test_zero_strict():
    os.environ["TOTP_VALID_WINDOW"] = "0"
    try:
        assert totp_valid_window() == 0
    finally:
        os.environ.pop("TOTP_VALID_WINDOW", None)
