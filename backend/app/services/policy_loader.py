"""W8-#3 — 정책 YAML/JSON 핫 리로드 패턴.

파일 mtime 폴링 기반 lazy reload. ABAC 룰·임계값 등 운영 중 변경되는 정책을
프로세스 재시작 없이 갱신.

사용:
    pol = PolicyFile("path/to/policy.yaml")
    data = pol.get()  # 매 호출마다 mtime 확인 후 변경 시 재로드
    pol.force_reload()  # admin API 트리거용

YAML 패키지 미설치 시 JSON 으로 폴백. ``backend/app/policies/*.json`` 디렉터리는
W5-#8 emotion_rules.json 패턴과 동일.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class PolicyFile:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._cached: Any = None
        self._mtime: float = 0.0
        self._last_error: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _parse(self, raw: str) -> Any:
        # YAML 우선 → 실패 시 JSON
        try:
            import yaml  # type: ignore
            return yaml.safe_load(raw)
        except ImportError:
            pass
        return json.loads(raw)

    def _read(self) -> Any:
        try:
            text = self._path.read_text(encoding="utf-8")
            data = self._parse(text)
            self._last_error = None
            return data
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def get(self, default: Any = None) -> Any:
        """mtime 변경 시 재로드 후 반환. 파일 없거나 파싱 실패 시 default."""
        with self._lock:
            try:
                stat = self._path.stat()
            except FileNotFoundError:
                self._last_error = "파일 없음"
                return default
            if stat.st_mtime != self._mtime:
                data = self._read()
                if data is not None:
                    self._cached = data
                    self._mtime = stat.st_mtime
            return self._cached if self._cached is not None else default

    def force_reload(self) -> dict:
        """admin API 트리거용. (loaded, mtime, error) 반환."""
        with self._lock:
            try:
                stat = self._path.stat()
            except FileNotFoundError:
                return {"loaded": False, "mtime": None, "error": "파일 없음"}
            data = self._read()
            if data is None:
                return {"loaded": False, "mtime": stat.st_mtime, "error": self._last_error}
            self._cached = data
            self._mtime = stat.st_mtime
            return {"loaded": True, "mtime": stat.st_mtime, "error": None}

    def status(self) -> dict:
        with self._lock:
            return {
                "path": str(self._path),
                "exists": self._path.is_file(),
                "mtime": self._mtime if self._mtime else None,
                "last_error": self._last_error,
                "cached": self._cached is not None,
            }


# 글로벌 레지스트리 — admin API 가 한 번에 모든 등록 정책 reload 가능
_REGISTRY: dict[str, PolicyFile] = {}
_REGISTRY_LOCK = threading.Lock()


def register_policy(name: str, path: str | os.PathLike[str]) -> PolicyFile:
    pol = PolicyFile(path)
    with _REGISTRY_LOCK:
        _REGISTRY[name] = pol
    return pol


def get_policy(name: str) -> PolicyFile | None:
    with _REGISTRY_LOCK:
        return _REGISTRY.get(name)


def reload_all() -> dict[str, dict]:
    with _REGISTRY_LOCK:
        items = list(_REGISTRY.items())
    return {name: pol.force_reload() for name, pol in items}


def list_policies() -> dict[str, dict]:
    with _REGISTRY_LOCK:
        items = list(_REGISTRY.items())
    return {name: pol.status() for name, pol in items}
