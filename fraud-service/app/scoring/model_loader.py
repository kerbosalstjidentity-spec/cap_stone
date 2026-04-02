"""
학습 산출 joblib 로드 — capstone `train_export_rf` 번들 형식.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib

from app.config import PROJECT_ROOT, settings


def resolve_model_path() -> Path | None:
    raw = settings.model_path or os.environ.get("MODEL_PATH")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p if p.exists() else None


def load_model_bundle() -> dict[str, Any] | None:
    path = resolve_model_path()
    if path is None:
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None
