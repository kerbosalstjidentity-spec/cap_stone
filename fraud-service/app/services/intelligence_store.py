"""
Layer 5 — ABE 암호화 사기 인텔리전스 공유 저장소.

교수님 연구 연계:
- "Secure Data Sharing with Fine-grained AC for IoT Data Marketplace" (TNSM)
- "Cross-domain Fine-grained AC for IoT Data Sharing in Metaverse" (TDSC)

기관 간 사기 패턴을 CP-ABE 접근 정책과 함께 저장·공유한다.
정책을 만족하는 기관만 패턴 세부 정보를 조회할 수 있다.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.abe_engine import evaluate_access_structure


@dataclass
class IntelligenceEntry:
    """공유 사기 인텔리전스 엔트리."""
    entry_id: str
    publisher_institution: str
    pattern_type: str           # BLACKLIST | PATTERN | SIGNATURE | METRIC
    summary: str                # 공개 요약 (비암호화)
    access_policy: str          # CP-ABE 접근 구조식
    detail: dict[str, Any]      # 정책 만족 시에만 공개되는 상세 정보
    published_at: str = ""
    tags: list[str] = field(default_factory=list)


class IntelligenceStore:
    """In-memory 인텔리전스 저장소."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[IntelligenceEntry] = []
        self._counter = 0

    def publish(
        self,
        publisher_institution: str,
        pattern_type: str,
        summary: str,
        access_policy: str,
        detail: dict[str, Any],
        tags: list[str] | None = None,
    ) -> IntelligenceEntry:
        """새 인텔리전스 엔트리 게시."""
        with self._lock:
            self._counter += 1
            entry = IntelligenceEntry(
                entry_id=f"INTEL-{self._counter:06d}",
                publisher_institution=publisher_institution,
                pattern_type=pattern_type,
                summary=summary,
                access_policy=access_policy,
                detail=detail,
                published_at=datetime.now(tz=timezone.utc).isoformat(),
                tags=tags or [],
            )
            self._entries.append(entry)
            return entry

    def query(
        self,
        user_attrs: set[str],
        pattern_type: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """인텔리전스 조회. 접근 정책에 따라 detail 필드를 필터링."""
        with self._lock:
            results = []
            for entry in self._entries:
                if pattern_type and entry.pattern_type != pattern_type:
                    continue
                if tag and tag not in entry.tags:
                    continue

                has_access = evaluate_access_structure(entry.access_policy, user_attrs)
                item = {
                    "entry_id": entry.entry_id,
                    "publisher_institution": entry.publisher_institution,
                    "pattern_type": entry.pattern_type,
                    "summary": entry.summary,
                    "access_policy": entry.access_policy,
                    "published_at": entry.published_at,
                    "tags": entry.tags,
                    "detail": entry.detail if has_access else "[ENCRYPTED: 접근 권한 부족]",
                    "has_access": has_access,
                }
                results.append(item)
            return results

    def count(self) -> int:
        with self._lock:
            return len(self._entries)


# 싱글턴
intelligence_store = IntelligenceStore()
