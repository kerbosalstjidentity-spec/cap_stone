"""
처리 건수 / action 분포 인메모리 통계 수집기.
routes_fraud.py evaluate 호출 시마다 record() 호출.
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class StatEntry:
    tx_id: str
    final_action: str
    triggered_rules: list[str]
    score: float
    amount: float
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


_MAX_ENTRIES = 10_000


class StatsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: deque[StatEntry] = deque(maxlen=_MAX_ENTRIES)

    def record(
        self,
        tx_id: str,
        final_action: str,
        triggered_rules: list[str],
        score: float,
        amount: float,
    ) -> None:
        with self._lock:
            self._entries.append(
                StatEntry(tx_id, final_action, triggered_rules, score, amount)
            )

    def summary(self) -> dict:
        with self._lock:
            entries = list(self._entries)
        total = len(entries)
        if total == 0:
            return {"total_evaluated": 0}

        action_counts = Counter(e.final_action for e in entries)
        rule_counts: Counter = Counter()
        for e in entries:
            rule_counts.update(e.triggered_rules)

        return {
            "total_evaluated": total,
            "action_distribution": {
                k: round(v / total, 4) for k, v in action_counts.items()
            },
            "action_counts": dict(action_counts),
            "top_triggered_rules": [r for r, _ in rule_counts.most_common(5)],
            "avg_score": round(sum(e.score for e in entries) / total, 4),
            "avg_amount": round(sum(e.amount for e in entries) / total),
        }

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


stats_collector = StatsCollector()
