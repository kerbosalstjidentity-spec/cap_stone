"""
학습 산출 joblib 로드 — capstone `train_export_rf` 번들 형식.

W6-#2: `@functools.lru_cache(maxsize=1)` 로 디스크 I/O 캐시.
번들 교체 시 ``clear_model_cache()`` 호출.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import joblib

from app.config import PROJECT_ROOT, settings


def resolve_model_path(raw: str | os.PathLike[str] | None = None) -> Path | None:
    if raw is None:
        raw = settings.model_path or os.environ.get("MODEL_PATH")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p if p.exists() else None


@functools.lru_cache(maxsize=1)
def _load_bundle_cached(path_str: str) -> dict[str, Any] | None:
    try:
        return joblib.load(path_str)
    except Exception:
        return None


def load_model_bundle(path: str | os.PathLike[str] | Path | None = None) -> dict[str, Any] | None:
    if path is None:
        resolved = resolve_model_path()
    else:
        resolved = path if isinstance(path, Path) else Path(path)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved
        if not resolved.exists():
            return None
    if resolved is None:
        return None
    return _load_bundle_cached(str(resolved))


def clear_model_cache() -> None:
    _load_bundle_cached.cache_clear()


def model_cache_info() -> dict[str, int]:
    info = _load_bundle_cached.cache_info()
    return {"hits": info.hits, "misses": info.misses, "currsize": info.currsize}
