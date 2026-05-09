"""
Layer 5 — ABE 암호화 사기 인텔리전스 공유 저장소.

교수님 연구 연계:
- "Secure Data Sharing with Fine-grained AC for IoT Data Marketplace" (TNSM)
- "Cross-domain Fine-grained AC for IoT Data Sharing in Metaverse" (TDSC)

기관 간 사기 패턴을 CP-ABE 접근 정책과 함께 저장·공유한다.
정책을 만족하는 기관만 패턴 세부 정보를 조회할 수 있다.

W2-#5: Redis 영속화.
- 키: intel:entries (List, LPUSH 으로 최신 우선 정렬, 직렬화 JSON)
       intel:counter (entry_id 발급용 INCR)
- Redis 미가용 시 in-memory list 폴백 (싱글 인스턴스 한정)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import redis as redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

from app.services.abe_engine import evaluate_access_structure

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
_LIST_KEY = "intel:entries"
_COUNTER_KEY = "intel:counter"
_MAX_LIST = 5000  # 가장 오래된 항목부터 LTRIM

_redis_client = None


def _get_redis():
    global _redis_client
    if not _HAS_REDIS or not REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
    except Exception as e:
        logger.warning("[intel-store] Redis 연결 실패: %s", e)
        _redis_client = None
    return _redis_client


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
    """Redis-backed 인텔리전스 저장소 (in-memory 폴백)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[IntelligenceEntry] = []  # 폴백 전용
        self._counter = 0  # 폴백 전용

    def _next_id(self) -> str:
        r = _get_redis()
        if r is not None:
            try:
                n = int(r.incr(_COUNTER_KEY))
                return f"INTEL-{n:06d}"
            except Exception as e:
                logger.warning("[intel-store] Redis incr 실패, 폴백: %s", e)
        with self._lock:
            self._counter += 1
            return f"INTEL-{self._counter:06d}"

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
        entry = IntelligenceEntry(
            entry_id=self._next_id(),
            publisher_institution=publisher_institution,
            pattern_type=pattern_type,
            summary=summary,
            access_policy=access_policy,
            detail=detail,
            published_at=datetime.now(tz=timezone.utc).isoformat(),
            tags=tags or [],
        )
        r = _get_redis()
        if r is not None:
            try:
                pipe = r.pipeline()
                pipe.lpush(_LIST_KEY, json.dumps(asdict(entry), default=str))
                pipe.ltrim(_LIST_KEY, 0, _MAX_LIST - 1)
                pipe.execute()
                return entry
            except Exception as e:
                logger.warning("[intel-store] Redis lpush 실패, 폴백: %s", e)
        with self._lock:
            self._entries.append(entry)
        return entry

    def _all_entries(self) -> list[IntelligenceEntry]:
        """현재 저장된 전체 항목을 시간 역순으로 반환."""
        r = _get_redis()
        if r is not None:
            try:
                raw = r.lrange(_LIST_KEY, 0, -1) or []
                out: list[IntelligenceEntry] = []
                for item in raw:
                    try:
                        d = json.loads(item)
                        out.append(IntelligenceEntry(**d))
                    except Exception:
                        continue
                return out
            except Exception as e:
                logger.warning("[intel-store] Redis lrange 실패, 폴백: %s", e)
        # W9-#15: lock 범위 축소 — lock 안에서는 shallow copy 만, reverse 는 밖에서
        with self._lock:
            snapshot = list(self._entries)
        return list(reversed(snapshot))

    def query(
        self,
        user_attrs: set[str],
        pattern_type: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """인텔리전스 조회. 접근 정책에 따라 detail 필드를 필터링.

        W9-#15: 응답 dict 의 ``detail`` 필드 타입은 ``dict[str, Any] | str``.
        - 정책 만족 (``has_access=True``): 원본 ``dict`` 그대로
        - 정책 불일치: ``"[ENCRYPTED: 접근 권한 부족]"`` 문자열
        호출자는 ``isinstance(d, dict)`` 또는 ``has_access`` 플래그로 분기 처리.
        """
        results = []
        for entry in self._all_entries():
            if pattern_type and entry.pattern_type != pattern_type:
                continue
            if tag and tag not in entry.tags:
                continue

            has_access = evaluate_access_structure(entry.access_policy, user_attrs)
            results.append({
                "entry_id": entry.entry_id,
                "publisher_institution": entry.publisher_institution,
                "pattern_type": entry.pattern_type,
                "summary": entry.summary,
                "access_policy": entry.access_policy,
                "published_at": entry.published_at,
                "tags": entry.tags,
                "detail": entry.detail if has_access else "[ENCRYPTED: 접근 권한 부족]",
                "has_access": has_access,
            })
        return results

    def count(self) -> int:
        r = _get_redis()
        if r is not None:
            try:
                return int(r.llen(_LIST_KEY))
            except Exception:
                pass
        with self._lock:
            return len(self._entries)


# 싱글턴
intelligence_store = IntelligenceStore()
