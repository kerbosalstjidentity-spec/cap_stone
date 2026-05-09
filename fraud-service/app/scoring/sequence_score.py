"""W7.5-#2 — 사용자 시퀀스 기반 정상도 점수.

블로그 14 §Track γ 확장 — 사용자별 직전 N건의 거래 시퀀스를 학습해
다음 거래의 정상도(이상도)를 예측한다. 단일 거래의 절대값이 아닌
**그 사용자의 평소 패턴과의 거리**가 핵심 시그널.

설계 결정:
- LSTM 학습 시퀀스(`backend/app/ml/forecasting.py`) 는 PyTorch 의존이 크고
  콜드 스타트(N=1~5) 에 약함 → 본 모듈은 **온라인 통계 기반 z-score**
  로 시작. amount·hour 두 축의 표준화 거리를 합성해 0~1 점수 산출.
- PyTorch 가 가용한 환경에서는 ``forecasting.SpendForecaster`` 로 보강
  가능하도록 인터페이스 유지 — 본 1차 구현은 통계만.
- 시퀀스 길이가 부족(< MIN_HISTORY)하면 cold-start 로 0.0 (정상) 반환.

이 점수는 ``ensemble`` 가중 합성 또는 ``rule_engine`` 의 보조 시그널로
활용 가능. 본 PR 에선 점수 산출 + 전용 라우트만 노출하고, 통합은 W7-#1
드리프트 라인업과 묶어서 처리한다.
"""
from __future__ import annotations

import math
import os
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

# 시퀀스 store 정책
DEFAULT_MAX_HISTORY = 20  # 사용자당 최대 보관 건수
MIN_HISTORY_FOR_SCORE = 5  # 이 미만이면 cold-start (점수=0)


@dataclass
class SeqEvent:
    amount: float
    hour: int  # 0~23, -1=미지정
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class SequenceStore:
    """사용자별 거래 시퀀스 deque (InMemory).

    Redis 백엔드는 W7-#1 드리프트 모듈과 합쳐서 후속 PR 에서 도입 예정 —
    1차 구현은 단일 인스턴스 가정으로 충분.
    """

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY) -> None:
        self._lock = threading.Lock()
        self._max = max_history
        self._by_user: dict[str, deque[SeqEvent]] = defaultdict(
            lambda: deque(maxlen=max_history)
        )

    def append(self, user_id: str, amount: float, hour: int) -> None:
        if not user_id:
            return
        with self._lock:
            self._by_user[user_id].append(
                SeqEvent(amount=float(amount), hour=int(hour))
            )

    def history(self, user_id: str) -> list[SeqEvent]:
        with self._lock:
            return list(self._by_user.get(user_id, ()))

    def length(self, user_id: str) -> int:
        with self._lock:
            return len(self._by_user.get(user_id, ()))

    def reset(self) -> None:
        with self._lock:
            self._by_user.clear()


sequence_store = SequenceStore(
    max_history=int(os.environ.get("SEQUENCE_MAX_HISTORY", DEFAULT_MAX_HISTORY))
)


def _zscore(x: float, values: list[float]) -> float:
    if not values:
        return 0.0
    mu = sum(values) / len(values)
    var = sum((v - mu) ** 2 for v in values) / len(values)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return 0.0
    return (x - mu) / sd


def _hour_anomaly(current_hour: int, history_hours: list[int]) -> float:
    """직전 hour 분포 대비 등장 빈도 → 0(친숙) ~ 1(처음).

    히스토리에 한 번도 없는 시간대면 1.0, 절반 이상 차지하면 0.0.
    """
    if current_hour < 0 or not history_hours:
        return 0.0
    valid = [h for h in history_hours if h >= 0]
    if not valid:
        return 0.0
    occurrences = valid.count(current_hour)
    return max(0.0, 1.0 - (occurrences / len(valid)))


def score_sequence(
    user_id: str,
    current_amount: float,
    current_hour: int,
    *,
    history: Iterable[SeqEvent] | None = None,
) -> dict:
    """사용자 직전 N건 대비 현재 거래의 이상도 점수(0~1).

    구성요소:
      - amount_z: 직전 amount 시퀀스 대비 |z| (clip 4 → /4 = 0~1)
      - hour_anomaly: 직전 hour 분포 대비 처음 등장도
      - sequence_score: 0.7 * amount_z_norm + 0.3 * hour_anomaly

    cold-start (history 길이 < MIN_HISTORY_FOR_SCORE) 시 sequence_score=0.0.
    """
    seq = list(history) if history is not None else sequence_store.history(user_id)
    n = len(seq)
    if n < MIN_HISTORY_FOR_SCORE:
        return {
            "user_id": user_id,
            "history_len": n,
            "cold_start": True,
            "amount_z": 0.0,
            "hour_anomaly": 0.0,
            "sequence_score": 0.0,
        }

    amounts = [e.amount for e in seq]
    hours = [e.hour for e in seq]

    z = abs(_zscore(float(current_amount), amounts))
    z_norm = min(z / 4.0, 1.0)
    h_anom = _hour_anomaly(int(current_hour), hours)
    score = round(0.7 * z_norm + 0.3 * h_anom, 4)

    return {
        "user_id": user_id,
        "history_len": n,
        "cold_start": False,
        "amount_z": round(z, 4),
        "hour_anomaly": round(h_anom, 4),
        "sequence_score": score,
    }
