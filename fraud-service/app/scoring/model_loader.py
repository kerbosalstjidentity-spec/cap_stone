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


# W6-#3: 번들 포맷 스키마 — 도메인별 필수 키 + 모델 인터페이스 검증.
# 검증 실패 시 None 반환 + 환경변수 ``MODEL_BUNDLE_STRICT=1`` 설정 시 예외 raise.

# domain → 필수 키 집합. 도메인 미지정/미상이면 ``open`` 폴백.
_REQUIRED_KEYS: dict[str, set[str]] = {
    "open": {"model"},
    "paysim": {"if_model", "rf_model", "raw_feature_names"},
}


class BundleSchemaError(ValueError):
    """번들 스키마 위반."""


def _has_predict_proba(obj: Any) -> bool:
    return obj is not None and callable(getattr(obj, "predict_proba", None))


def validate_bundle(bundle: Any) -> tuple[bool, list[str]]:
    """번들 구조/모델 인터페이스 검증. (ok, problems[]) 반환.

    검증 항목:
    - dict 타입
    - domain 별 필수 키 존재
    - open: ``model.predict_proba`` 콜러블
    - paysim: ``if_model.score_samples`` + ``rf_model.predict_proba`` 콜러블
              + raw_feature_names 비-empty 리스트
    - 선택 키 (feature_mu/std, anomaly_low/high) 가 있으면 길이 정합성 검증
    """
    problems: list[str] = []
    if not isinstance(bundle, dict):
        return False, [f"번들이 dict 가 아님: {type(bundle).__name__}"]

    domain = str(bundle.get("domain", "open"))
    required = _REQUIRED_KEYS.get(domain, _REQUIRED_KEYS["open"])
    missing = required - set(bundle.keys())
    if missing:
        problems.append(f"필수 키 누락 (domain={domain}): {sorted(missing)}")

    if domain == "open":
        if not _has_predict_proba(bundle.get("model")):
            problems.append("model.predict_proba 콜러블 아님")
    elif domain == "paysim":
        if not callable(getattr(bundle.get("if_model"), "score_samples", None)):
            problems.append("if_model.score_samples 콜러블 아님")
        if not _has_predict_proba(bundle.get("rf_model")):
            problems.append("rf_model.predict_proba 콜러블 아님")
        rfn = bundle.get("raw_feature_names")
        if not isinstance(rfn, list) or len(rfn) == 0:
            problems.append("raw_feature_names 가 비-empty 리스트 아님")

    # 선택 키 정합성 (있으면 검사)
    mu = bundle.get("feature_mu")
    std = bundle.get("feature_std")
    if mu is not None and std is not None:
        try:
            if len(mu) != len(std):
                problems.append(f"feature_mu/std 길이 불일치: {len(mu)} vs {len(std)}")
        except TypeError:
            problems.append("feature_mu/std 가 시퀀스 아님")

    lo = bundle.get("anomaly_low")
    hi = bundle.get("anomaly_high")
    if lo is not None and hi is not None:
        try:
            if float(lo) >= float(hi):
                problems.append(
                    f"anomaly_low({lo}) >= anomaly_high({hi})"
                )
        except (TypeError, ValueError):
            problems.append("anomaly_low/high 가 숫자 아님")

    return len(problems) == 0, problems


@functools.lru_cache(maxsize=1)
def _load_bundle_cached(path_str: str) -> dict[str, Any] | None:
    try:
        bundle = joblib.load(path_str)
    except Exception:
        return None
    ok, problems = validate_bundle(bundle)
    if not ok:
        msg = f"번들 스키마 검증 실패 ({path_str}): {'; '.join(problems)}"
        if os.environ.get("MODEL_BUNDLE_STRICT", "").lower() in ("1", "true", "yes"):
            raise BundleSchemaError(msg)
        # 비-strict 모드에선 None 반환 (운영 안전)
        import logging
        logging.getLogger(__name__).warning(msg)
        return None
    return bundle


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
