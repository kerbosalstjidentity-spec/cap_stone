"""
다차원 Rule Engine.

각 Rule은 tx dict + UserProfile(optional)을 받아 (action, rule_id) 반환.
RuleEngine이 모든 규칙을 평가하고 가장 강한 action을 선택.
기존 policy_merge.merge_actions 재활용.

W2-#4: 룰 토글 상태(enabled)를 Redis 해시에 영속화.
- 키: rule:toggles → Hash {rule_id: "1"|"0"}
- toggle_rule() 호출 시 즉시 Redis 갱신 + 메모리 반영
- 엔진 init 시 Redis에서 토글 상태 로드 (재시작 후에도 유지)
- evaluate_all() 에서 enabled=False 룰을 실제로 스킵하도록 fix
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import redis as redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

from app.services.policy_merge import ACTION_RANK, RANK_TO_ACTION, merge_actions
from app.services.profile_store import UserProfile

logger = logging.getLogger(__name__)
_REDIS_URL = os.getenv("REDIS_URL", "")
_TOGGLE_KEY = "rule:toggles"
_redis_client = None


def _get_redis():
    global _redis_client
    if not _HAS_REDIS or not _REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
    except Exception as e:
        logger.warning("[rule-toggle] Redis 연결 실패: %s", e)
        _redis_client = None
    return _redis_client


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


class MoneyMuleRule(Rule):
    """머니뮬 hub-spoke 패턴 (W6.5-#3).

    송금자(현재 거래의 user_id) 가 ``fan_in_count`` 명 이상에게서 받은 후
    ``pass_through_ratio`` 이상 통과시키는 패턴이면 BLOCK.

    입력: tx['graph_features'] (W6.5-#2 extract_all 결과). 미존재 시 미발동.
    """
    rule_id = "MONEY_MULE_HUB"

    def __init__(self, min_fan_in: int = 3, pass_through_ratio_threshold: float = 0.8) -> None:
        self.min_fan_in = min_fan_in
        self.pass_through_ratio_threshold = pass_through_ratio_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        feats = tx.get("graph_features") or {}
        fan_in = int(feats.get("sender_fan_in_count", 0) or 0)
        ratio = float(feats.get("sender_pass_through_ratio", 0.0) or 0.0)
        if fan_in >= self.min_fan_in and ratio >= self.pass_through_ratio_threshold:
            return RuleResult(
                self.rule_id,
                "BLOCK",
                f"hub-spoke: fan_in={fan_in}≥{self.min_fan_in}, pass_through={ratio:.2f}≥{self.pass_through_ratio_threshold}",
            )
        return None


class LayeringRule(Rule):
    """다단계 자금세탁 체인 (W6.5-#4).

    A→B→C 형태로 짧은 시간 내에 받은 만큼 거의 그대로 통과시키는 패턴.
    머니뮬과의 차이점: hub 가 아니라 *체인* — fan_in 이 작아도 (1~2)
    inbound 직후(``≤recent_inbound_threshold_min``) outbound 가 나가는
    "잔액 통과" 행위를 잡는다.

    조건: sender_pass_through_ratio ≥ ratio_threshold AND
          sender_recent_inbound_min_ago ≤ recent_inbound_threshold_min AND
          sender_fan_in_count < hub_fan_in_threshold (mule 룰과 분리)
    Action: REVIEW (mule 룰의 BLOCK 보다 약하게 — 체인 한 단계만 보고
    판단하는 데 따른 보수성)
    """
    rule_id = "LAYERING_CHAIN"

    def __init__(
        self,
        ratio_threshold: float = 0.9,
        recent_inbound_threshold_min: float = 10.0,
        hub_fan_in_threshold: int = 3,
    ) -> None:
        self.ratio_threshold = ratio_threshold
        self.recent_inbound_threshold_min = recent_inbound_threshold_min
        self.hub_fan_in_threshold = hub_fan_in_threshold

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        feats = tx.get("graph_features") or {}
        ratio = float(feats.get("sender_pass_through_ratio", 0.0) or 0.0)
        recent_min = float(feats.get("sender_recent_inbound_min_ago", 9999.0) or 9999.0)
        fan_in = int(feats.get("sender_fan_in_count", 0) or 0)
        if (
            ratio >= self.ratio_threshold
            and recent_min <= self.recent_inbound_threshold_min
            and fan_in < self.hub_fan_in_threshold
        ):
            return RuleResult(
                self.rule_id,
                "REVIEW",
                f"layering chain: pass_through={ratio:.2f}≥{self.ratio_threshold}, "
                f"inbound {recent_min:.1f}min ago, fan_in={fan_in}<{self.hub_fan_in_threshold}",
            )
        return None


class BalanceDrainRule(Rule):
    """잔액 급변 패턴 (W7.5-#1).

    CASH_OUT/TRANSFER 컨텍스트에서 송금 전 잔액의 ``drain_ratio_threshold``
    이상이 빠지고 동시에 ``amount`` 가 ``amount_threshold`` 이상이면 BLOCK.
    계정 탈취 직후 자금 전액 인출 시나리오 대응.

    False-positive 방어:
    - ``oldbalanceOrg < min_old_balance`` 면 미발동 (잔액 정보 없음/소액)
    - type 필드가 있고 CASH_OUT/TRANSFER 가 아니면 미발동

    PaySim 컬럼명 호환: ``oldbalanceOrg`` + ``newbalanceOrig`` 우선,
    ``newbalanceOrg`` 별칭도 허용.
    """
    rule_id = "BALANCE_DRAIN"

    def __init__(
        self,
        drain_ratio_threshold: float = 0.9,
        amount_threshold: float = 500_000,
        min_old_balance: float = 100_000,
    ) -> None:
        self.drain_ratio_threshold = drain_ratio_threshold
        self.amount_threshold = amount_threshold
        self.min_old_balance = min_old_balance

    def evaluate(self, tx, profile):
        if not self.enabled:
            return None
        type_str = str(tx.get("type", "") or "").upper()
        if type_str and type_str not in {"CASH_OUT", "TRANSFER"}:
            return None
        old = float(tx.get("oldbalanceOrg", 0) or 0)
        if old < self.min_old_balance:
            return None
        new_raw = tx.get("newbalanceOrig")
        if new_raw is None:
            new_raw = tx.get("newbalanceOrg")
        new = float(new_raw or 0)
        amount = float(tx.get("amount", 0) or 0)
        if amount < self.amount_threshold:
            return None
        drain = (old - new) / old
        if drain >= self.drain_ratio_threshold:
            return RuleResult(
                self.rule_id,
                "BLOCK",
                f"drain {drain*100:.1f}%≥{self.drain_ratio_threshold*100:.0f}%, "
                f"amount {amount:,.0f}≥{self.amount_threshold:,.0f}",
            )
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
            MoneyMuleRule(),           # W6.5-#3 — graph_features 기반
            LayeringRule(),            # W6.5-#4 — 체인 패턴
            BalanceDrainRule(),        # W7.5-#1 — 잔액 급변 인출
            AmountBlockRule(),
            AmountReviewRule(),
            TimeRiskRule(),
            VelocityRule(),
            SplitTransactionRule(),
            ForeignIpRule(),
            AmountSpikeRule(),
            NewMerchantRule(),
        ]

        # W2-#4: Redis에서 토글 상태 로드 (있으면 적용)
        self._load_toggles_from_redis()

    # ── W2-#4: Redis 토글 영속화 헬퍼 ────────────────────
    def _load_toggles_from_redis(self) -> None:
        r = _get_redis()
        if r is None:
            return
        try:
            toggles = r.hgetall(_TOGGLE_KEY) or {}
            if not toggles:
                return
            for rule in self._rules:
                v = toggles.get(rule.rule_id)
                if v is not None:
                    rule.enabled = v == "1"
            logger.info("[rule-toggle] Redis에서 %d건 토글 상태 로드", len(toggles))
        except Exception as e:
            logger.warning("[rule-toggle] Redis 로드 실패: %s", e)

    def _persist_toggle(self, rule_id: str, enabled: bool) -> None:
        r = _get_redis()
        if r is None:
            return
        try:
            r.hset(_TOGGLE_KEY, rule_id, "1" if enabled else "0")
        except Exception as e:
            logger.warning("[rule-toggle] Redis 저장 실패: %s", e)

    # 외부 조회용
    def list_rules(self) -> list[dict]:
        with self._lock:
            return [
                {"rule_id": r.rule_id, "enabled": r.enabled, "type": type(r).__name__}
                for r in self._rules
            ]

    def toggle_rule(self, rule_id: str) -> bool | None:
        """토글 성공 시 새 enabled 값 반환, 없으면 None.

        W2-#4: Redis hash에 즉시 영속화.
        """
        with self._lock:
            for r in self._rules:
                if r.rule_id == rule_id:
                    r.enabled = not r.enabled
                    new_enabled = r.enabled
                    break
            else:
                return None
        # 락 밖에서 Redis I/O (블로킹 최소화)
        self._persist_toggle(rule_id, new_enabled)
        return new_enabled

    def evaluate_all(
        self, tx: dict[str, Any], profile: UserProfile | None
    ) -> list[RuleResult]:
        with self._lock:
            rules = list(self._rules)
        results = []
        for rule in rules:
            # W2-#4 부수 효과 fix: 토글 OFF 룰 스킵 (이전엔 enabled 무시되고 평가됨)
            if not getattr(rule, "enabled", True):
                continue
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
