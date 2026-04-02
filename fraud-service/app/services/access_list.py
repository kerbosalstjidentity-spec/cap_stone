"""
Blacklist / Whitelist 인메모리 저장소.

- Blacklist: user_id 또는 IP → 즉시 BLOCK
- Whitelist: user_id → Rule Engine 건너뜀, 모델 스코어만 반영

Rule Engine에서 가장 먼저 체크.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class ListEntry:
    value: str
    kind: Literal["user_id", "ip"]
    reason: str = ""
    added_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AccessListStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blacklist: dict[str, ListEntry] = {}  # key = f"{kind}:{value}"
        self._whitelist: set[str] = set()           # user_id only

    # --- Blacklist ---
    def blacklist_add(self, kind: Literal["user_id", "ip"], value: str, reason: str = "") -> None:
        with self._lock:
            self._blacklist[f"{kind}:{value}"] = ListEntry(value=value, kind=kind, reason=reason)

    def blacklist_remove(self, kind: Literal["user_id", "ip"], value: str) -> bool:
        with self._lock:
            return self._blacklist.pop(f"{kind}:{value}", None) is not None

    def is_blacklisted(self, user_id: str = "", ip: str = "") -> ListEntry | None:
        with self._lock:
            if user_id and (e := self._blacklist.get(f"user_id:{user_id}")):
                return e
            if ip and (e := self._blacklist.get(f"ip:{ip}")):
                return e
        return None

    def blacklist_all(self) -> list[dict]:
        with self._lock:
            return [
                {"kind": e.kind, "value": e.value, "reason": e.reason,
                 "added_at": e.added_at.isoformat()}
                for e in self._blacklist.values()
            ]

    # --- Whitelist ---
    def whitelist_add(self, user_id: str) -> None:
        with self._lock:
            self._whitelist.add(user_id)

    def whitelist_remove(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._whitelist:
                self._whitelist.discard(user_id)
                return True
        return False

    def is_whitelisted(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._whitelist

    def whitelist_all(self) -> list[str]:
        with self._lock:
            return sorted(self._whitelist)


access_list = AccessListStore()
