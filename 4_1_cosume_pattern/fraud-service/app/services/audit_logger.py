"""
구조화된 Audit log → logs/audit.jsonl (append-only).

각 evaluate 호출마다 한 줄씩 JSON 기록.
로그 로테이션: 파일 크기 MAX_BYTES 초과 시 자동 rotate (backup 3개).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOG_DIR = Path(os.getenv("AUDIT_LOG_DIR", "logs"))
_LOG_FILE = _LOG_DIR / "audit.jsonl"
_MAX_BYTES = int(os.getenv("AUDIT_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
_BACKUP_COUNT = 3

_lock = threading.Lock()
_handler: RotatingFileHandler | None = None


def _get_handler() -> RotatingFileHandler:
    global _handler
    if _handler is None:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    return _handler


def write(
    tx_id: str,
    user_id: str,
    final_action: str,
    rule_id: str,
    score: float,
    amount: float,
    reason_code: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "tx_id": tx_id,
        "user_id": user_id,
        "final_action": final_action,
        "rule_id": rule_id or None,
        "score": round(score, 6),
        "amount": amount,
        "reason_code": reason_code or None,
        **(extra or {}),
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        h = _get_handler()
        h.stream.write(line + "\n")
        h.stream.flush()
        # rotate 체크: 파일 크기 직접 비교
        try:
            if _LOG_FILE.stat().st_size >= _MAX_BYTES:
                h.doRollover()
        except OSError:
            pass


def tail(n: int = 50) -> list[dict]:
    """최근 n줄 반환 (Admin 대시보드용)."""
    if not _LOG_FILE.exists():
        return []
    with _lock:
        lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:] if len(lines) > n else lines
    result = []
    for line in reversed(recent):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result
