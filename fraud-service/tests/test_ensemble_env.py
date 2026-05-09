"""W9-#3 — ALPHA/BETA env 외부화 테스트."""
from __future__ import annotations

import importlib
import os


def test_default_weights():
    os.environ.pop("ENSEMBLE_ALPHA", None)
    os.environ.pop("ENSEMBLE_BETA", None)
    from app.scoring import ensemble
    importlib.reload(ensemble)
    assert ensemble.ALPHA == 0.7
    assert ensemble.BETA == 0.3


def test_env_override():
    os.environ["ENSEMBLE_ALPHA"] = "0.55"
    os.environ["ENSEMBLE_BETA"] = "0.45"
    try:
        from app.scoring import ensemble
        importlib.reload(ensemble)
        assert ensemble.ALPHA == 0.55
        assert ensemble.BETA == 0.45
    finally:
        os.environ.pop("ENSEMBLE_ALPHA", None)
        os.environ.pop("ENSEMBLE_BETA", None)
        from app.scoring import ensemble
        importlib.reload(ensemble)


def test_invalid_env_falls_back():
    os.environ["ENSEMBLE_ALPHA"] = "not_a_number"
    try:
        from app.scoring import ensemble
        importlib.reload(ensemble)
        assert ensemble.ALPHA == 0.7
    finally:
        os.environ.pop("ENSEMBLE_ALPHA", None)
        from app.scoring import ensemble
        importlib.reload(ensemble)
