"""송금 그래프 store (W6.5-#1) — sender → receiver 엣지 sorted set + TTL.

블로그 12 §Track 4 — PaySim 의 nameOrig/nameDest 정보를 활용해 머니뮬·hub-spoke
패턴을 검출하기 위한 그래프 피처(W6.5-#2 ``graph_features.py``) 의 입력 store.

키 모델 (Redis sorted set):
    inbound:{receiver}    score=ts  member=f"{sender}|{amount}|{tx_id}|{ts}"
    outbound:{sender}     score=ts  member=f"{receiver}|{amount}|{tx_id}|{ts}"

각 엣지를 양방향 인덱스에 적재해 fan-in / fan-out / pass-through 같은
W6.5-#2 피처를 모두 sorted set 윈도우 쿼리로 답할 수 있게 한다.

device_store.py 패턴을 답습 — Redis 미가용 시 in-memory deque 폴백.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

try:
    import redis as redis_lib  # type: ignore

    _HAS_REDIS = True
except ImportError:  # pragma: no cover
    _HAS_REDIS = False
    redis_lib = None  # type: ignore

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
_WINDOW_MINUTES = int(os.getenv("GRAPH_WINDOW_MINUTES", "60"))
_KEY_TTL_S = int(os.getenv("GRAPH_STORE_TTL_S", str(_WINDOW_MINUTES * 60 * 4)))  # 4× 윈도우
_MAX_PER_NODE = int(os.getenv("GRAPH_MAX_PER_NODE", "1000"))
_KEY_INBOUND_PREFIX = "graph:inbound:"
_KEY_OUTBOUND_PREFIX = "graph:outbound:"

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
        logger.info("[graph-store] Redis 연결 성공")
    except Exception as e:
        logger.warning("[graph-store] Redis 연결 실패, in-memory 폴백: %s", e)
        _redis_client = None
    return _redis_client


@dataclass
class Edge:
    """sender → receiver 한 건의 송금 엣지."""
    sender: str
    receiver: str
    amount: float
    tx_id: str = ""
    ts: float = 0.0  # epoch seconds


def _encode(member_node: str, amount: float, tx_id: str, ts: float) -> str:
    # `|` 가 nameOrig/nameDest 에 없는 PaySim 특성 활용. 안전 보강용으로 escape 가능하나 현 단계 단순.
    return f"{member_node}|{amount}|{tx_id}|{ts}"


def _decode(member: str) -> tuple[str, float, str, float]:
    parts = member.split("|", 3)
    while len(parts) < 4:
        parts.append("")
    node, amt, tx_id, ts = parts
    try:
        amount = float(amt)
    except ValueError:
        amount = 0.0
    try:
        ts_f = float(ts)
    except ValueError:
        ts_f = 0.0
    return node, amount, tx_id, ts_f


class GraphStore:
    """송금 그래프 — Redis sorted set 양방향 인덱스, in-memory 폴백."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 폴백 — node → deque[Edge]
        self._inbound: dict[str, deque[Edge]] = defaultdict(lambda: deque(maxlen=_MAX_PER_NODE))
        self._outbound: dict[str, deque[Edge]] = defaultdict(lambda: deque(maxlen=_MAX_PER_NODE))

    # ── key helpers ────────────────────────────
    @staticmethod
    def _inbound_key(receiver: str) -> str:
        return f"{_KEY_INBOUND_PREFIX}{receiver}"

    @staticmethod
    def _outbound_key(sender: str) -> str:
        return f"{_KEY_OUTBOUND_PREFIX}{sender}"

    # ── 쓰기 ──────────────────────────────────
    def record(self, sender: str, receiver: str, amount: float, *, tx_id: str = "", ts: float | None = None) -> None:
        """엣지 1건 적재. sender/receiver 비면 무시."""
        if not sender or not receiver:
            return
        now_ts = ts if ts is not None else time.time()
        amount_f = float(amount)

        r = _get_redis()
        if r is not None:
            try:
                ib_key = self._inbound_key(receiver)
                ob_key = self._outbound_key(sender)
                cutoff = now_ts - (_WINDOW_MINUTES * 60)
                pipe = r.pipeline()
                pipe.zadd(ib_key, {_encode(sender, amount_f, tx_id, now_ts): now_ts})
                pipe.zadd(ob_key, {_encode(receiver, amount_f, tx_id, now_ts): now_ts})
                pipe.zremrangebyscore(ib_key, 0, cutoff)
                pipe.zremrangebyscore(ob_key, 0, cutoff)
                pipe.expire(ib_key, _KEY_TTL_S)
                pipe.expire(ob_key, _KEY_TTL_S)
                pipe.execute()
                return
            except Exception as e:
                logger.warning("[graph-store] Redis zadd 실패, 폴백: %s", e)

        edge = Edge(sender=sender, receiver=receiver, amount=amount_f, tx_id=tx_id, ts=now_ts)
        with self._lock:
            self._inbound[receiver].append(edge)
            self._outbound[sender].append(edge)

    # ── 읽기 ──────────────────────────────────
    def _read_window(self, key: str, fallback: dict[str, deque[Edge]], node: str, window_minutes: int) -> list[Edge]:
        now_ts = time.time()
        cutoff = now_ts - (window_minutes * 60)
        r = _get_redis()
        if r is not None:
            try:
                members = r.zrangebyscore(key, cutoff, now_ts)
                edges: list[Edge] = []
                for m in members:
                    other, amount, tx_id, ts = _decode(m)
                    edges.append(Edge(
                        sender=other if key.startswith(_KEY_INBOUND_PREFIX) else node,
                        receiver=node if key.startswith(_KEY_INBOUND_PREFIX) else other,
                        amount=amount, tx_id=tx_id, ts=ts,
                    ))
                return edges
            except Exception as e:
                logger.warning("[graph-store] Redis zrangebyscore 실패, 폴백: %s", e)
        cutoff_ts = now_ts - (window_minutes * 60)
        with self._lock:
            records = list(fallback.get(node, []))
        return [e for e in records if e.ts >= cutoff_ts]

    def inbound(self, receiver: str, window_minutes: int = _WINDOW_MINUTES) -> list[Edge]:
        """receiver 가 받은 송금 엣지 리스트 (윈도우 내, 시간 오름차순)."""
        if not receiver:
            return []
        return self._read_window(self._inbound_key(receiver), self._inbound, receiver, window_minutes)

    def outbound(self, sender: str, window_minutes: int = _WINDOW_MINUTES) -> list[Edge]:
        """sender 가 보낸 송금 엣지 리스트."""
        if not sender:
            return []
        return self._read_window(self._outbound_key(sender), self._outbound, sender, window_minutes)

    # ── 편의 집계 ─────────────────────────────
    def fan_in_count(self, receiver: str, window_minutes: int = _WINDOW_MINUTES) -> int:
        """receiver 에게 들어온 distinct sender 수."""
        edges = self.inbound(receiver, window_minutes)
        return len({e.sender for e in edges})

    def inbound_amount(self, receiver: str, window_minutes: int = _WINDOW_MINUTES) -> float:
        return sum(e.amount for e in self.inbound(receiver, window_minutes))

    def outbound_amount(self, sender: str, window_minutes: int = _WINDOW_MINUTES) -> float:
        return sum(e.amount for e in self.outbound(sender, window_minutes))

    def first_seen_ts(self, node: str) -> float | None:
        """receiver 가 우리 그래프에 처음 나타난 timestamp.

        ``inbound`` 의 가장 오래된 엣지 ts. 없으면 None.
        """
        if not node:
            return None
        # 윈도우 무관하게 충분히 큰 값 사용 (TTL 한계로 제한됨)
        edges = self.inbound(node, window_minutes=10**6)
        if not edges:
            return None
        return min(e.ts for e in edges)

    # ── 테스트/관리 ──────────────────────────
    def clear(self, nodes: Iterable[str] | None = None) -> None:
        """주어진 노드(또는 전체) 의 in/out 인덱스 삭제. 테스트 전용."""
        r = _get_redis()
        if nodes is None:
            with self._lock:
                self._inbound.clear()
                self._outbound.clear()
            if r is not None:
                try:
                    cursor = 0
                    while True:
                        cursor, keys = r.scan(cursor, match=f"{_KEY_INBOUND_PREFIX}*", count=200)
                        if keys:
                            r.delete(*keys)
                        if cursor == 0:
                            break
                    cursor = 0
                    while True:
                        cursor, keys = r.scan(cursor, match=f"{_KEY_OUTBOUND_PREFIX}*", count=200)
                        if keys:
                            r.delete(*keys)
                        if cursor == 0:
                            break
                except Exception as e:
                    logger.warning("[graph-store] clear all 실패: %s", e)
            return
        for n in nodes:
            with self._lock:
                self._inbound.pop(n, None)
                self._outbound.pop(n, None)
            if r is not None:
                try:
                    r.delete(self._inbound_key(n), self._outbound_key(n))
                except Exception as e:
                    logger.warning("[graph-store] clear %s 실패: %s", n, e)


graph_store = GraphStore()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)
