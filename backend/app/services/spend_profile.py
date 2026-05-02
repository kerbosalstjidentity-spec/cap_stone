"""소비 프로필 관리 — 인메모리 저장소 (Phase 1) + DB 재수화 (W2-#6).

fraud-service의 profile_store.py 패턴을 따르되,
소비 분석에 필요한 카테고리별 집계를 추가.

W2-#6: DB(`Transaction` 테이블)가 단일 정본.
- 신규 거래는 routes_seed/ingest API 가 `spend_profile_db.ingest_batch` 로 DB 영속화
- 메모리 store 는 분석용 캐시 — 서버 부팅 시 `rehydrate_from_db()` 가 DB에서
  최근 N일 거래를 읽어 자동 복원 → 재시작 후에도 분석 결과 일관
- 추후 spend_profile_db 의 async API 로 모든 read path 를 옮기면 본 모듈은 deprecated
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.schemas.spend import (
    CategorySummary,
    SpendCategory,
    SpendProfile,
    TransactionIngest,
)

logger = logging.getLogger(__name__)


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

    async def rehydrate_from_db(self, days: int = 180) -> int:
        """W2-#6: DB의 Transaction 테이블에서 최근 N일을 읽어 메모리에 복원.

        서버 재시작 후에도 분석 캐시가 빈 상태로 시작하지 않도록 보장.
        """
        try:
            from sqlalchemy import select
            from app.db.session import async_session_factory
            from app.models.tables import Transaction
        except Exception as e:
            logger.warning("[spend_profile] rehydrate 의존성 로드 실패: %s", e)
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        replayed = 0
        try:
            async with async_session_factory() as session:
                rows = await session.execute(
                    select(Transaction).where(Transaction.timestamp >= cutoff)
                )
                for r in rows.scalars().all():
                    try:
                        cat = SpendCategory(r.category) if r.category else SpendCategory.OTHER
                    except ValueError:
                        cat = SpendCategory.OTHER
                    tx = TransactionIngest(
                        transaction_id=r.transaction_id,
                        user_id=r.user_id,
                        amount=float(r.amount),
                        timestamp=r.timestamp,
                        merchant_id=r.merchant_id or "",
                        category=cat,
                        channel=r.channel or "online",
                        is_domestic=bool(r.is_domestic),
                        memo=r.memo or "",
                    )
                    self.ingest(tx)
                    replayed += 1
            logger.info("[spend_profile] rehydrate 완료: %d txs (최근 %d일)", replayed, days)
        except Exception as e:
            logger.warning("[spend_profile] rehydrate 실패 (DB 미준비?): %s", e)
        return replayed


# 싱글턴
profile_store = InMemorySpendProfileStore()
