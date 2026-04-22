"""ML 모델 학습/재학습 파이프라인.

PostgreSQL에서 거래 데이터를 읽어 4가지 모델을 학습:
  - K-Means 소비 유형 군집화
  - XGBoost 과소비 분류
  - Isolation Forest 이상 탐지
  - LSTM 월별 예측

서버 시작 시 자동 실행하거나, API 엔드포인트로 수동 트리거 가능.
"""

import logging
from collections import defaultdict

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.anomaly import anomaly_detector
from app.ml.classifier import overspend_classifier
from app.ml.clustering import FEATURE_CATEGORIES, cluster_model
from app.ml.forecasting import forecaster
from app.models.tables import Transaction, User
from app.schemas.spend import SpendCategory

logger = logging.getLogger(__name__)

CATEGORY_INDEX = {c.value: i for i, c in enumerate(SpendCategory)}


async def train_all(session: AsyncSession) -> dict:
    """모든 ML 모델 학습. 반환값은 각 모델 학습 결과 요약."""
    results = {}

    results["clustering"] = await _train_clustering(session)
    results["anomaly"] = await _train_anomaly(session)
    results["classifier"] = await _train_classifier(session)
    results["forecaster"] = await _train_forecaster(session)

    logger.info("ML training complete: %s", results)
    return results


# ──────────────────────────────────────────────
#  K-Means 군집화
# ──────────────────────────────────────────────

async def _train_clustering(session: AsyncSession) -> dict:
    """사용자별 카테고리 지출 비율로 K-Means 학습."""
    result = await session.execute(
        select(
            Transaction.user_id,
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .group_by(Transaction.user_id, Transaction.category)
    )
    rows = result.all()
    if not rows:
        return {"status": "skipped", "reason": "no_data"}

    # 사용자별 카테고리 총액 집계
    user_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    user_grand: dict[str, float] = defaultdict(float)
    for r in rows:
        user_totals[r.user_id][r.category] += r.total
        user_grand[r.user_id] += r.total

    # 비율로 변환
    profiles = []
    for uid, cats in user_totals.items():
        grand = user_grand[uid]
        if grand <= 0:
            continue
        pct = {cat: amt / grand for cat, amt in cats.items()}
        profiles.append(pct)

    if len(profiles) < cluster_model.n_clusters:
        return {"status": "skipped", "reason": "insufficient_users", "count": len(profiles)}

    cluster_model.fit(profiles)
    return {"status": "trained", "n_users": len(profiles)}


# ──────────────────────────────────────────────
#  Isolation Forest 이상 탐지
# ──────────────────────────────────────────────

async def _train_anomaly(session: AsyncSession) -> dict:
    """전체 거래 데이터로 Isolation Forest 학습."""
    result = await session.execute(
        select(
            Transaction.amount,
            func.extract("hour", Transaction.timestamp).label("hour"),
            Transaction.is_domestic,
            Transaction.category,
        )
        .order_by(func.random())
        .limit(10000)
    )
    rows = result.all()
    if len(rows) < 10:
        return {"status": "skipped", "reason": "insufficient_data", "count": len(rows)}

    transactions = [
        {
            "amount": r.amount,
            "hour": int(r.hour) if r.hour is not None else 12,
            "is_domestic": r.is_domestic,
            "category_idx": CATEGORY_INDEX.get(r.category, 0),
        }
        for r in rows
    ]

    anomaly_detector.fit(transactions)
    return {"status": "trained", "n_samples": len(transactions)}


# ──────────────────────────────────────────────
#  XGBoost 과소비 분류
# ──────────────────────────────────────────────

async def _train_classifier(session: AsyncSession) -> dict:
    """거래 데이터에서 특성을 추출하여 XGBoost 학습.

    과소비 레이블: 사용자 월평균의 2배 이상 지출한 건 = 1
    """
    # 사용자별 월평균 계산
    avg_result = await session.execute(
        select(
            Transaction.user_id,
            func.avg(Transaction.amount).label("avg_amt"),
            func.sum(Transaction.amount).label("total"),
            func.count().label("cnt"),
        )
        .group_by(Transaction.user_id)
    )
    user_stats = {r.user_id: {"avg": r.avg_amt, "monthly_avg": r.total / max(1, r.cnt) * 30} for r in avg_result.all()}

    if not user_stats:
        return {"status": "skipped", "reason": "no_users"}

    # 카테고리별 비율
    cat_result = await session.execute(
        select(
            Transaction.user_id,
            Transaction.category,
            func.sum(Transaction.amount).label("cat_total"),
        )
        .group_by(Transaction.user_id, Transaction.category)
    )
    user_cat_pct: dict[str, dict[str, float]] = defaultdict(dict)
    user_cat_total: dict[str, float] = defaultdict(float)
    for r in cat_result.all():
        user_cat_pct[r.user_id][r.category] = r.cat_total
        user_cat_total[r.user_id] += r.cat_total
    for uid in user_cat_pct:
        total = user_cat_total[uid]
        if total > 0:
            user_cat_pct[uid] = {k: v / total for k, v in user_cat_pct[uid].items()}

    # 거래 샘플링
    tx_result = await session.execute(
        select(
            Transaction.user_id,
            Transaction.amount,
            func.extract("hour", Transaction.timestamp).label("hour"),
            Transaction.is_domestic,
            Transaction.category,
        )
        .order_by(func.random())
        .limit(5000)
    )
    txs = tx_result.all()
    if len(txs) < 10:
        return {"status": "skipped", "reason": "insufficient_data"}

    X_list, y_list = [], []
    for tx in txs:
        stats = user_stats.get(tx.user_id)
        if not stats:
            continue
        avg_amt = stats["avg"]
        cat_pct = user_cat_pct.get(tx.user_id, {}).get(tx.category, 0.1)
        hour = int(tx.hour) if tx.hour is not None else 12

        features = [
            tx.amount,
            tx.amount / avg_amt if avg_amt > 0 else 0,
            cat_pct,
            hour,
            1 if tx.is_domestic else 0,
            1.0,  # monthly_total_ratio (simplified)
            10,   # tx_frequency placeholder
        ]
        X_list.append(features)
        # 레이블: 평균의 2배 이상이면 과소비
        y_list.append(1 if tx.amount > avg_amt * 2 else 0)

    X = np.array(X_list)
    y = np.array(y_list)

    result = overspend_classifier.fit(X, y)
    return result


# ──────────────────────────────────────────────
#  LSTM 월별 예측
# ──────────────────────────────────────────────

async def _train_forecaster(session: AsyncSession) -> dict:
    """전체 월별 총 지출 시계열로 LSTM 학습."""
    result = await session.execute(
        select(
            func.to_char(Transaction.timestamp, "YYYY-MM").label("period"),
            func.sum(Transaction.amount).label("total"),
        )
        .group_by(text("1"))   # PostgreSQL: GROUP BY 위치 참조 (파라미터 바인딩 충돌 방지)
        .order_by(text("1"))
    )
    rows = result.all()
    if len(rows) < forecaster.seq_length + 1:
        return {"status": "skipped", "reason": "insufficient_months", "count": len(rows)}

    monthly_totals = [float(r.total) for r in rows]
    result = forecaster.train(monthly_totals)
    return result
