"""
다차원 Rule Engine.

각 Rule은 tx dict + UserProfile(optional)을 받아 (action, rule_id) 반환.
RuleEngine이 모든 규칙을 평가하고 가장 강한 action을 선택.
기존 policy_merge.merge_actions 재활용.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.policy_merge import ACTION_RANK, RANK_TO_ACTION, merge_actions
from app.services.profile_store import UserProfile


# ---------------------------------------------------------------------------
# Rule 기반 클래스
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    rule_id: str
    action: str
    detail: str = ""


class Rule(ABC):
    rule_id: str
    enabled: bool = True

    @abstractmethod
    def evaluate(self, tx: dict[str, Any], profile: UserProfile | None) -> RuleResult | None:
        """발동 시 RuleResult 반환, 미발동 시 None."""


# ---------------------------------------------------------------------------
# 구체 규칙들
# ---------------------------------------------------------------------------

class AmountBlockRule(Rule):
    """금액 ≥ block_threshold → BLOCK (기존 로직 이식)."""
    rule_id = "AMOUNT_BLOCK"

    def __init__(self, block_threshold: float = 5_000_000) -> None:
        self.block_threshold = block_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        amount = float(tx.get("amount", 0))
        if amount >= self.block_threshold:
            return RuleResult(self.rule_id, "BLOCK", f"{amount:,.0f}원 ≥ {self.block_threshold:,.0f}원")
        return None


class AmountReviewRule(Rule):
    """금액 ≥ review_threshold → REVIEW."""
    rule_id = "AMOUNT_REVIEW"

    def __init__(self, review_threshold: float = 1_000_000) -> None:
        self.review_threshold = review_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        amount = float(tx.get("amount", 0))
        if amount >= self.review_threshold:
            return RuleResult(self.rule_id, "REVIEW", f"{amount:,.0f}원 ≥ {self.review_threshold:,.0f}원")
        return None


class TimeRiskRule(Rule):
    """새벽 02:00~05:00 AND 금액 ≥ threshold → REVIEW."""
    rule_id = "TIME_RISK"

    def __init__(self, start_hour: int = 2, end_hour: int = 5, amount_threshold: float = 500_000) -> None:
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.amount_threshold = amount_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        hour = tx.get("hour", -1)
        if hour == -1:
            ts = tx.get("timestamp")
            if isinstance(ts, str):
                try:
                    hour = datetime.fromisoformat(ts).hour
                except ValueError:
                    return None
            else:
                return None
        amount = float(tx.get("amount", 0))
        if self.start_hour <= hour < self.end_hour and amount >= self.amount_threshold:
            return RuleResult(self.rule_id, "REVIEW", f"새벽 {hour}시 {amount:,.0f}원")
        return None


class VelocityRule(Rule):
    """최근 velocity_window 분 내 건수 ≥ max_count → BLOCK."""
    rule_id = "VELOCITY_FREQ"

    def __init__(self, window_minutes: int = 10, max_count: int = 3) -> None:
        self.window_minutes = window_minutes
        self.max_count = max_count

    def evaluate(self, tx, profile):
        if not self.enabled or profile is None:
            return None
        window_key = f"{self.window_minutes}m" if self.window_minutes in (1, 5, 15) else "5m"
        count = profile.velocity.get(window_key, 0)
        if count >= self.max_count:
            return RuleResult(self.rule_id, "BLOCK", f"{self.window_minutes}분 내 {count}건")
        return None


class SplitTransactionRule(Rule):
    """소액 쪼개기 탐지: 금액 ≤ threshold 이면서 1분 내 velocity ≥ min_count → REVIEW."""
    rule_id = "SPLIT_TXN"

    def __init__(self, amount_max: float = 100_000, min_count: int = 5) -> None:
        self.amount_max = amount_max
        self.min_count = min_count

    def evaluate(self, tx, profile):
        if not self.enabled or profile is None:
            return None
        amount = float(tx.get("amount", 0))
        if amount <= self.amount_max and profile.velocity.get("1m", 0) >= self.min_count:
            return RuleResult(self.rule_id, "REVIEW", f"1분 내 {profile.velocity['1m']}건 소액 쪼개기 의심")
        return None


class ForeignIpRule(Rule):
    """해외 IP AND 금액 ≥ threshold → REVIEW."""
    rule_id = "FOREIGN_IP"

    def __init__(self, amount_threshold: float = 300_000) -> None:
        self.amount_threshold = amount_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        if tx.get("is_foreign_ip") and float(tx.get("amount", 0)) >= self.amount_threshold:
            return RuleResult(self.rule_id, "REVIEW", f"해외 IP {tx.get('ip', '')} {tx.get('amount', 0):,.0f}원")
        return None


class AmountSpikeRule(Rule):
    """금액 > 사용자 평균 × spike_multiplier → SOFT_REVIEW."""
    rule_id = "AMOUNT_SPIKE"

    def __init__(self, spike_multiplier: float = 5.0, min_avg: float = 10_000) -> None:
        self.spike_multiplier = spike_multiplier
        self.min_avg = min_avg

    def evaluate(self, tx, profile):
        if not self.enabled or profile is None:
            return None
        avg = profile.avg_amount
        if avg < self.min_avg:
            return None
        amount = float(tx.get("amount", 0))
        if amount > avg * self.spike_multiplier:
            return RuleResult(self.rule_id, "SOFT_REVIEW", f"{amount:,.0f}원 > 평균 {avg:,.0f}원의 {self.spike_multiplier}배")
        return None


class DeviceFingerprintRule(Rule):
    """같은 device_id로 window 분 내 max_users명 이상의 user_id 거래 → REVIEW."""
    rule_id = "DEVICE_FINGERPRINT"

    def __init__(self, window_minutes: int = 60, max_users: int = 2) -> None:
        self.window_minutes = window_minutes
        self.max_users = max_users

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        device_id = tx.get("device_id", "")
        user_id = tx.get("user_id", "")
        if not device_id or not user_id:
            return None
        from app.services.device_store import device_store
        device_store.record(device_id, user_id)
        users = device_store.unique_users_in_window(device_id, self.window_minutes)
        if len(users) >= self.max_users:
            return RuleResult(
                self.rule_id, "REVIEW",
                f"device {device_id}: {self.window_minutes}분 내 {len(users)}개 계정 사용"
            )
        return None


class BlacklistRule(Rule):
    """Blacklist user_id 또는 IP → 즉시 BLOCK."""
    rule_id = "BLACKLIST"

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        from app.services.access_list import access_list
        entry = access_list.is_blacklisted(
            user_id=tx.get("user_id", ""),
            ip=tx.get("ip", ""),
        )
        if entry:
            return RuleResult(self.rule_id, "BLOCK", f"블랙리스트: {entry.kind}={entry.value} ({entry.reason})")
        return None


class NewMerchantRule(Rule):
    """처음 거래하는 merchant AND 금액 ≥ threshold → SOFT_REVIEW."""
    rule_id = "NEW_MERCHANT"

    def __init__(self, amount_threshold: float = 200_000) -> None:
        self.amount_threshold = amount_threshold

    def evaluate(self, tx, profile):
        if not self.enabled or profile is None:
            return None
        # profile에 거래 이력이 있고, merchant_diversity가 1이면 첫 거래 merchant일 가능성 높음
        # 실제로는 profile에 merchant 목록이 있어야 하지만 현재는 다양성 0인 경우만 체크
        merchant = tx.get("merchant_id", "")
        if not merchant:
            return None
        if profile.tx_count <= 1 and float(tx.get("amount", 0)) >= self.amount_threshold:
            return RuleResult(self.rule_id, "SOFT_REVIEW", f"신규 merchant {merchant} {tx.get('amount', 0):,.0f}원")
        return None


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------

class RuleEngine:
    """
    등록된 Rule 목록을 모두 평가, 가장 강한 action 반환.
    스레드 세이프 (enabled 토글용 lock).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rules: list[Rule] = [
            BlacklistRule(),           # 최우선
            DeviceFingerprintRule(),
            AmountBlockRule(),
            AmountReviewRule(),
            TimeRiskRule(),
            VelocityRule(),
            SplitTransactionRule(),
            ForeignIpRule(),
            AmountSpikeRule(),
            NewMerchantRule(),
        ]

    # 외부 조회용
    def list_rules(self) -> list[dict]:
        with self._lock:
            return [
                {"rule_id": r.rule_id, "enabled": r.enabled, "type": type(r).__name__}
                for r in self._rules
            ]

    def toggle_rule(self, rule_id: str) -> bool | None:
        """토글 성공 시 새 enabled 값 반환, 없으면 None."""
        with self._lock:
            for r in self._rules:
                if r.rule_id == rule_id:
                    r.enabled = not r.enabled
                    return r.enabled
        return None

    def evaluate_all(
        self, tx: dict[str, Any], profile: UserProfile | None
    ) -> list[RuleResult]:
        with self._lock:
            rules = list(self._rules)
        results = []
        for rule in rules:
            res = rule.evaluate(tx, profile)
            if res is not None:
                results.append(res)
        return results

    def get_strongest(self, results: list[RuleResult]) -> tuple[str, str]:
        """(action, rule_ids 콤마 구분) 반환. 결과 없으면 ('PASS', '')."""
        if not results:
            return "PASS", ""
        best = max(results, key=lambda r: ACTION_RANK.get(r.action, 0))
        rule_ids = ",".join(r.rule_id for r in results)
        return best.action, rule_ids


# 싱글턴
rule_engine = RuleEngine()
