"""W7-#4 — 분포 변화 임계값 알람 + 자동 롤백.

drift_detector / stats_collector 의 신호를 임계값과 비교해 트리거 시
앙상블 가중치를 (0, 0) 으로 강제(즉시 롤백)하고 감사 로그를 남긴다.

자동 모니터 루프는 운영 환경에서 docker compose / systemd 가 별도 워치독
프로세스를 띄우는 가정. 본 모듈은 (1) `check_and_act()` 단발 호출 + (2)
admin API 트리거 + (3) `restore_default_weights()` 만 제공.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.scoring import ensemble
from app.services import audit_logger
from app.services.drift_detector import drift_detector
from app.services.stats_collector import stats_collector


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# 임계값 — env 로 운영 중 조정 가능
DRIFT_KS_THRESHOLD = _env_float("ALARM_DRIFT_KS", 0.30)
SCORE_P99_DELTA_THRESHOLD = _env_float("ALARM_SCORE_P99_DELTA", 0.30)
DEFAULT_ALPHA = _env_float("ENSEMBLE_ALPHA", 0.7)
DEFAULT_BETA = _env_float("ENSEMBLE_BETA", 0.3)


@dataclass
class AlarmState:
    rolled_back: bool = False
    last_check_at: str | None = None
    last_reason: str | None = None
    last_signals: dict = field(default_factory=dict)
    saved_alpha: float | None = None
    saved_beta: float | None = None


class AlarmManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = AlarmState()

    def state(self) -> dict:
        with self._lock:
            return {
                "rolled_back": self._state.rolled_back,
                "last_check_at": self._state.last_check_at,
                "last_reason": self._state.last_reason,
                "last_signals": dict(self._state.last_signals),
                "saved_weights": (
                    {"alpha": self._state.saved_alpha, "beta": self._state.saved_beta}
                    if self._state.saved_alpha is not None
                    else None
                ),
                "current_weights": ensemble.get_weights(),
            }

    def _collect_signals(self) -> dict:
        signals: dict = {}
        # drift
        try:
            rep = drift_detector.report(threshold=DRIFT_KS_THRESHOLD)
            signals["drift_any"] = bool(rep.get("any_drift"))
            signals["drift_per_feature"] = {
                k: {"ks": v["ks"], "drifted": v["drifted"]}
                for k, v in rep.get("per_feature", {}).items()
            }
        except Exception as exc:  # pragma: no cover
            signals["drift_error"] = str(exc)
        # score p99 일별 변화
        try:
            sd = stats_collector.score_distribution_daily(days=2)
            per_day = sd.get("per_day", [])
            if len(per_day) == 2:
                yesterday, today = per_day
                signals["score_p99_yesterday"] = yesterday["p99"]
                signals["score_p99_today"] = today["p99"]
                signals["score_p99_delta"] = round(
                    today["p99"] - yesterday["p99"], 4
                )
                signals["score_p99_delta_exceeded"] = (
                    yesterday["count"] > 0
                    and today["count"] > 0
                    and abs(signals["score_p99_delta"]) >= SCORE_P99_DELTA_THRESHOLD
                )
            else:
                signals["score_p99_delta_exceeded"] = False
        except Exception as exc:  # pragma: no cover
            signals["score_error"] = str(exc)
        return signals

    def check_and_act(self, *, force: bool = False) -> dict:
        signals = self._collect_signals()
        reasons: list[str] = []
        if signals.get("drift_any"):
            reasons.append("drift")
        if signals.get("score_p99_delta_exceeded"):
            reasons.append("score_p99_delta")
        if force:
            reasons.append("forced")

        with self._lock:
            self._state.last_check_at = datetime.now(tz=timezone.utc).isoformat()
            self._state.last_signals = signals
            triggered = bool(reasons) and not self._state.rolled_back
            if triggered:
                cur = ensemble.get_weights()
                self._state.saved_alpha = cur["alpha"]
                self._state.saved_beta = cur["beta"]
                ensemble.set_weights(alpha=0.0, beta=0.0)
                self._state.rolled_back = True
                self._state.last_reason = ",".join(reasons)
                try:
                    audit_logger.write(
                        tx_id="ALARM-ROLLBACK",
                        user_id="system",
                        final_action="ROLLBACK",
                        rule_id="auto_rollback",
                        score=0.0,
                        amount=0.0,
                        reason_code=";".join(reasons),
                    )
                except Exception:  # pragma: no cover
                    pass
            return {
                "checked": True,
                "triggered": triggered,
                "already_rolled_back": self._state.rolled_back and not triggered,
                "reasons": reasons,
                "signals": signals,
                "weights_after": ensemble.get_weights(),
            }

    def restore_default_weights(self) -> dict:
        with self._lock:
            alpha = self._state.saved_alpha if self._state.saved_alpha is not None else DEFAULT_ALPHA
            beta = self._state.saved_beta if self._state.saved_beta is not None else DEFAULT_BETA
            ensemble.set_weights(alpha=alpha, beta=beta)
            self._state.rolled_back = False
            self._state.saved_alpha = None
            self._state.saved_beta = None
            self._state.last_reason = "restored"
            try:
                audit_logger.write(
                    tx_id="ALARM-RESTORE",
                    user_id="system",
                    final_action="RESTORE",
                    rule_id="auto_rollback",
                    score=0.0,
                    amount=0.0,
                    reason_code="restored",
                )
            except Exception:  # pragma: no cover
                pass
            return {"restored": True, "weights": ensemble.get_weights()}

    def reset(self) -> None:
        with self._lock:
            self._state = AlarmState()


alarm_manager = AlarmManager()
