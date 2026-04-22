"""소비 프로필 관리 — 인메모리 저장소 (Phase 1).

fraud-service의 profile_store.py 패턴을 따르되,
소비 분석에 필요한 카테고리별 집계를 추가.
"""

from collections import defaultdict
from datetime import datetime

from app.schemas.spend import (
    CategorySummary,
    SpendCategory,
    SpendProfile,
    TransactionIngest,
)


class _UserStore:
    """단일 유저의 거래 이력 + 집계."""

    def __init__(self) -> None:
        self.transactions: list[TransactionIngest] = []
        self.category_totals: dict[SpendCategory, float] = defaultdict(float)
        self.category_counts: dict[SpendCategory, int] = defaultdict(int)
        self.hour_counts: dict[int, int] = defaultdict(int)
        self.max_amount: float = 0.0

    def add(self, tx: TransactionIngest) -> None:
        self.transactions.append(tx)
        self.category_totals[tx.category] += tx.amount
        self.category_counts[tx.category] += 1
        self.hour_counts[tx.timestamp.hour] += 1
        if tx.amount > self.max_amount:
            self.max_amount = tx.amount


class InMemorySpendProfileStore:
    """인메모리 소비 프로필 저장소."""

    def __init__(self) -> None:
        self._users: dict[str, _UserStore] = {}

    def ingest(self, tx: TransactionIngest) -> None:
        if tx.user_id not in self._users:
            self._users[tx.user_id] = _UserStore()
        self._users[tx.user_id].add(tx)

    def get_profile(self, user_id: str) -> SpendProfile | None:
        store = self._users.get(user_id)
        if not store or not store.transactions:
            return None

        total_amount = sum(store.category_totals.values())
        tx_count = len(store.transactions)
        peak_hour = max(store.hour_counts, key=store.hour_counts.get) if store.hour_counts else 0
        top_cat = max(store.category_totals, key=store.category_totals.get) if store.category_totals else SpendCategory.OTHER

        breakdown = []
        for cat in SpendCategory:
            cat_total = store.category_totals.get(cat, 0.0)
            cat_count = store.category_counts.get(cat, 0)
            if cat_count == 0:
                continue
            breakdown.append(
                CategorySummary(
                    category=cat,
                    total_amount=cat_total,
                    tx_count=cat_count,
                    avg_amount=cat_total / cat_count,
                    pct_of_total=cat_total / total_amount if total_amount > 0 else 0,
                )
            )

        timestamps = [tx.timestamp for tx in store.transactions]

        return SpendProfile(
            user_id=user_id,
            total_tx_count=tx_count,
            total_amount=total_amount,
            avg_amount=total_amount / tx_count,
            max_amount=store.max_amount,
            peak_hour=peak_hour,
            top_category=top_cat,
            category_breakdown=sorted(breakdown, key=lambda x: x.total_amount, reverse=True),
            period_start=min(timestamps),
            period_end=max(timestamps),
        )

    def get_transactions(self, user_id: str) -> list[TransactionIngest]:
        store = self._users.get(user_id)
        return list(store.transactions) if store else []

    def get_trend(self, user_id: str) -> dict[str, dict[str, float]]:
        """월별 카테고리 지출 추이."""
        txs = self.get_transactions(user_id)
        if not txs:
            return {}

        monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for tx in txs:
            key = tx.timestamp.strftime("%Y-%m")
            monthly[key][tx.category.value] += tx.amount
            monthly[key]["_total"] += tx.amount

        return {k: dict(v) for k, v in sorted(monthly.items())}

    def delete_user(self, user_id: str) -> bool:
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False


# 싱글턴
profile_store = InMemorySpendProfileStore()
