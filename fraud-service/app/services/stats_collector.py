"""처리 건수 / action 분포 / latency / 시나리오별 검출률 인메모리 통계 수집기.

W7.5-#6 확장 — 시나리오별 검출률·latency p50/p99·FN/FP 시계열을 SLO
대시보드에서 노출하기 위해 record() 시 latency_ms·scenario_label·
expected_action 을 함께 적재한다.

기본 record() 시그니처는 후방 호환 — 신규 필드는 모두 default=None.
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# tx_id prefix → scenario_label 자동 매핑 (scenario_generator + 적대적 회귀)
_SCENARIO_PREFIX: dict[str, str] = {
    "VP": "VOICE_PHISHING",
    "MM": "MONEY_MULE",
    "ATO": "ACCOUNT_TAKEOVER",
    "CT": "CARD_TESTING",
    "MMC": "MONEY_MULE_CHAIN",  # W7.5-#5 적대적
    "SMR": "SMURFING",          # W7.5-#5 적대적
    "COS": "CASH_OUT_SPLIT",    # W7.5-#5 적대적
}

_DETECT_ACTIONS = {"BLOCK", "REVIEW"}


def _infer_scenario(tx_id: str) -> str | None:
    if not tx_id or "-" not in tx_id:
        return None
    prefix = tx_id.split("-", 1)[0]
    return _SCENARIO_PREFIX.get(prefix)


@dataclass
class StatEntry:
    tx_id: str
    final_action: str
    triggered_rules: list[str]
    score: float
    amount: float
    latency_ms: float | None = None
    scenario_label: str | None = None
    expected_action: str | None = None  # ground truth (시나리오는 BLOCK/REVIEW 기대)
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


_MAX_ENTRIES = 10_000


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


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
        latency_ms: float | None = None,
        scenario_label: str | None = None,
        expected_action: str | None = None,
    ) -> None:
        if scenario_label is None:
            scenario_label = _infer_scenario(tx_id)
        # 시나리오가 식별되면 기본 ground truth 는 "검출되어야 함"
        if expected_action is None and scenario_label is not None:
            expected_action = "DETECT"  # BLOCK or REVIEW 둘 다 정답
        with self._lock:
            self._entries.append(
                StatEntry(
                    tx_id=tx_id,
                    final_action=final_action,
                    triggered_rules=triggered_rules,
                    score=score,
                    amount=amount,
                    latency_ms=latency_ms,
                    scenario_label=scenario_label,
                    expected_action=expected_action,
                )
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

    # --- W7.5-#6: SLO 대시보드 전용 집계 ---

    def slo_summary(self, *, bucket_minutes: int = 1, buckets: int = 60) -> dict:
        """시나리오별 검출률 + latency p50/p99 + FN/FP + 시계열.

        - per_scenario: {label: {total, detected, detection_rate, fn, fp, avg_latency_ms, p99_latency_ms}}
        - latency: 전체 평균/p50/p99
        - timeseries: 최근 ``buckets`` 개 윈도우(``bucket_minutes`` 분)별 detection_rate·p99
        """
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return {
                "total_evaluated": 0,
                "per_scenario": {},
                "latency": {"avg_ms": 0.0, "p50_ms": 0.0, "p99_ms": 0.0},
                "timeseries": [],
            }

        # 시나리오별 집계
        per_scn: dict[str, dict] = defaultdict(
            lambda: {
                "total": 0,
                "detected": 0,
                "fn": 0,
                "fp": 0,
                "latencies": [],
            }
        )
        all_latencies: list[float] = []
        for e in entries:
            if e.latency_ms is not None:
                all_latencies.append(e.latency_ms)
            scn = e.scenario_label or "UNLABELED"
            slot = per_scn[scn]
            slot["total"] += 1
            detected = e.final_action in _DETECT_ACTIONS
            if detected:
                slot["detected"] += 1
            # FN: 검출되어야 했는데 PASS — 시나리오 라벨이 있으면 detected 가 정답
            if e.expected_action == "DETECT" and not detected:
                slot["fn"] += 1
            # FP: 검출 안 되어야 했는데 BLOCK/REVIEW
            if e.expected_action == "PASS" and detected:
                slot["fp"] += 1
            if e.latency_ms is not None:
                slot["latencies"].append(e.latency_ms)

        per_scenario_out: dict[str, dict] = {}
        for label, slot in per_scn.items():
            tot = slot["total"] or 1
            lats = slot["latencies"]
            per_scenario_out[label] = {
                "total": slot["total"],
                "detected": slot["detected"],
                "detection_rate": round(slot["detected"] / tot, 4),
                "fn": slot["fn"],
                "fp": slot["fp"],
                "fn_rate": round(slot["fn"] / tot, 4),
                "fp_rate": round(slot["fp"] / tot, 4),
                "avg_latency_ms": round(sum(lats) / len(lats), 3) if lats else 0.0,
                "p99_latency_ms": round(_percentile(lats, 99), 3) if lats else 0.0,
            }

        # 시계열: 최근 buckets * bucket_minutes 분
        now = datetime.now(tz=timezone.utc)
        bucket_seconds = bucket_minutes * 60
        ts_buckets: dict[int, dict[str, list]] = defaultdict(
            lambda: {"detected": 0, "total": 0, "latencies": []}
        )
        for e in entries:
            delta = (now - e.ts).total_seconds()
            if delta < 0 or delta > buckets * bucket_seconds:
                continue
            idx = int(delta // bucket_seconds)
            b = ts_buckets[idx]
            b["total"] += 1
            if e.final_action in _DETECT_ACTIONS:
                b["detected"] += 1
            if e.latency_ms is not None:
                b["latencies"].append(e.latency_ms)

        timeseries: list[dict] = []
        for idx in range(buckets):
            b = ts_buckets.get(idx)
            if b is None or b["total"] == 0:
                continue
            lats = b["latencies"]
            timeseries.append({
                "minutes_ago": idx * bucket_minutes,
                "total": b["total"],
                "detection_rate": round(b["detected"] / b["total"], 4),
                "p99_latency_ms": round(_percentile(lats, 99), 3) if lats else 0.0,
            })
        timeseries.sort(key=lambda x: x["minutes_ago"])

        return {
            "total_evaluated": len(entries),
            "per_scenario": per_scenario_out,
            "latency": {
                "avg_ms": round(sum(all_latencies) / len(all_latencies), 3) if all_latencies else 0.0,
                "p50_ms": round(_percentile(all_latencies, 50), 3) if all_latencies else 0.0,
                "p99_ms": round(_percentile(all_latencies, 99), 3) if all_latencies else 0.0,
            },
            "timeseries": timeseries,
        }

    # --- W7-#3: 점수 분포 일별 모니터링 ---

    def score_distribution_daily(self, *, days: int = 7) -> dict:
        """최근 ``days`` 일 동안 일자별 점수 분포 (UTC 기준).

        per_day 배열: [{date, count, mean, p50, p95, p99, min, max,
        action_block_rate}]. 분포 변화(W7-#4 자동 롤백 트리거)·이상 시점 추적용.
        """
        with self._lock:
            entries = list(self._entries)
        days = max(1, min(days, 90))
        now = datetime.now(tz=timezone.utc)
        cutoff = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        buckets: dict[str, list[StatEntry]] = defaultdict(list)
        for e in entries:
            if e.ts < cutoff:
                continue
            key = e.ts.strftime("%Y-%m-%d")
            buckets[key].append(e)

        per_day: list[dict] = []
        for i in range(days):
            day = (cutoff + timedelta(days=i)).strftime("%Y-%m-%d")
            day_entries = buckets.get(day, [])
            if not day_entries:
                per_day.append({
                    "date": day,
                    "count": 0,
                    "mean": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "block_rate": 0.0,
                })
                continue
            scores = [e.score for e in day_entries]
            blocks = sum(1 for e in day_entries if e.final_action == "BLOCK")
            per_day.append({
                "date": day,
                "count": len(day_entries),
                "mean": round(sum(scores) / len(scores), 4),
                "p50": round(_percentile(scores, 50), 4),
                "p95": round(_percentile(scores, 95), 4),
                "p99": round(_percentile(scores, 99), 4),
                "min": round(min(scores), 4),
                "max": round(max(scores), 4),
                "block_rate": round(blocks / len(day_entries), 4),
            })

        # 전체 요약 (참조용)
        all_scores = [e.score for e in entries if e.ts >= cutoff]
        overall = {
            "count": len(all_scores),
            "mean": round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0,
            "p50": round(_percentile(all_scores, 50), 4) if all_scores else 0.0,
            "p95": round(_percentile(all_scores, 95), 4) if all_scores else 0.0,
            "p99": round(_percentile(all_scores, 99), 4) if all_scores else 0.0,
        }
        return {"days": days, "per_day": per_day, "overall": overall}

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


stats_collector = StatsCollector()
