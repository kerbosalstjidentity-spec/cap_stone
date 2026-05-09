"""W7.5-#4 — chargeback 피드백 루프 ground truth 라벨 저장소.

지급결제 chargeback (사기 신고로 인한 매출 환불) 이벤트를 기록해
"실제 사기였던 tx_id" 의 ground truth 라벨을 누적한다.

stats_collector 의 평가 이력과 join 하면 일별/시나리오별 precision/recall
계산 가능 (W7-#9 ground truth 메트릭에서 활용).

InMemory 기본 + Redis Hash 백엔드(선택). ``profile_store`` / ``stepup_store``
와 동일 패턴 — 환경변수 ``FEEDBACK_STORE_REDIS=1`` 시 Redis 사용.
"""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Redis 는 선택적 — 미설치 환경에서도 InMemory 폴백
try:  # pragma: no cover
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


@dataclass
class ChargebackEntry:
    tx_id: str
    user_id: str
    amount: float
    reason: str = ""
    reported_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    label: str = "FRAUD"  # ground truth — chargeback 은 항상 FRAUD


class _InMemoryFeedbackStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_tx: dict[str, ChargebackEntry] = {}

    def record(
        self,
        *,
        tx_id: str,
        user_id: str,
        amount: float,
        reason: str = "",
        label: str = "FRAUD",
    ) -> ChargebackEntry:
        entry = ChargebackEntry(
            tx_id=tx_id,
            user_id=user_id,
            amount=float(amount),
            reason=reason,
            label=label,
        )
        with self._lock:
            self._by_tx[tx_id] = entry
        return entry

    def get(self, tx_id: str) -> ChargebackEntry | None:
        with self._lock:
            return self._by_tx.get(tx_id)

    def all(self) -> list[ChargebackEntry]:
        with self._lock:
            return list(self._by_tx.values())

    def count(self) -> int:
        with self._lock:
            return len(self._by_tx)

    def clear(self) -> None:
        with self._lock:
            self._by_tx.clear()


class _RedisFeedbackStore:  # pragma: no cover - 통합 환경에서만
    """Redis Hash 백엔드. key=feedback:chargeback, field=tx_id, value=JSON."""

    KEY = "feedback:chargeback"

    def __init__(self, client: Any) -> None:
        import json as _json
        self._client = client
        self._json = _json

    def record(
        self,
        *,
        tx_id: str,
        user_id: str,
        amount: float,
        reason: str = "",
        label: str = "FRAUD",
    ) -> ChargebackEntry:
        entry = ChargebackEntry(
            tx_id=tx_id,
            user_id=user_id,
            amount=float(amount),
            reason=reason,
            label=label,
        )
        self._client.hset(self.KEY, tx_id, self._json.dumps(asdict(entry)))
        return entry

    def get(self, tx_id: str) -> ChargebackEntry | None:
        raw = self._client.hget(self.KEY, tx_id)
        if not raw:
            return None
        data = self._json.loads(raw)
        return ChargebackEntry(**data)

    def all(self) -> list[ChargebackEntry]:
        items = self._client.hgetall(self.KEY) or {}
        out = []
        for v in items.values():
            try:
                out.append(ChargebackEntry(**self._json.loads(v)))
            except Exception:
                continue
        return out

    def count(self) -> int:
        return int(self._client.hlen(self.KEY) or 0)

    def clear(self) -> None:
        self._client.delete(self.KEY)


def _build_store():
    if os.environ.get("FEEDBACK_STORE_REDIS", "").lower() in ("1", "true", "yes"):
        if redis is None:
            return _InMemoryFeedbackStore()
        try:  # pragma: no cover
            url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return _RedisFeedbackStore(client)
        except Exception:
            return _InMemoryFeedbackStore()
    return _InMemoryFeedbackStore()


feedback_store = _build_store()


def precision_recall_summary(stats_entries: list[Any]) -> dict[str, Any]:
    """평가 이력(StatEntry list) + chargeback 라벨로 precision/recall 계산.

    - TP: chargeback 등록(FRAUD) AND 평가 시 BLOCK/REVIEW
    - FN: chargeback 등록(FRAUD) AND 평가 시 PASS/SOFT_REVIEW
    - FP: chargeback 미등록 AND 평가 시 BLOCK/REVIEW
    - TN: chargeback 미등록 AND 평가 시 PASS/SOFT_REVIEW

    chargeback 미등록 = ground truth 가 "정상"이라는 가정. 운영상 일부
    fraud 가 chargeback 으로 신고되지 않을 수 있어 FP 를 과대 추정할 수 있음
    (한계는 ROADMAP W7-#9 에서 운영 메트릭으로 보강).
    """
    detect = {"BLOCK", "REVIEW"}
    cb_ids = {e.tx_id for e in feedback_store.all()}
    tp = fn = fp = tn = 0
    for e in stats_entries:
        is_fraud = e.tx_id in cb_ids
        is_detected = e.final_action in detect
        if is_fraud and is_detected:
            tp += 1
        elif is_fraud and not is_detected:
            fn += 1
        elif not is_fraud and is_detected:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "chargeback_total": len(cb_ids),
        "evaluated_total": len(list(stats_entries)),
    }
