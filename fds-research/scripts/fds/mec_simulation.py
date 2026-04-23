"""
MEC (Multi-access Edge Computing) 실시간 거래 승인 시뮬레이션.

SRS 3 FR-04 요구사항:
- 에지 노드 기반 지연 모델링 (MEC vs Cloud 비교)
- UAC (User Access Control) 정책 기반 승인 한도 제어
- 실시간 거래 승인/거부 시뮬레이션

교수님 연구 연계:
- "Fine-Grained Access Control for Financial Data on MEC"
"""
from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ── MEC 노드 모델 ─────────────────────────────────────────────

@dataclass
class MECNode:
    """에지 노드 정의."""
    node_id: str
    region: str                     # seoul, busan, daegu, ...
    base_latency_ms: float          # 기본 처리 지연 (ms)
    capacity_tps: int               # 초당 처리 가능 건수
    current_load: float = 0.0       # 0.0 ~ 1.0
    is_active: bool = True

    @property
    def effective_latency_ms(self) -> float:
        """부하에 따른 실효 지연."""
        # 부하 50% 이상부터 지수적 지연 증가
        load_factor = 1.0 + max(0, self.current_load - 0.5) ** 2 * 10
        return self.base_latency_ms * load_factor


@dataclass
class CloudNode:
    """중앙 클라우드 노드."""
    node_id: str = "cloud-central"
    base_latency_ms: float = 150.0   # 클라우드 왕복 기본 지연
    network_jitter_ms: float = 30.0  # 네트워크 변동


# ── UAC 정책 ──────────────────────────────────────────────────

@dataclass
class UACPolicy:
    """UAC (User Access Control) 정책.

    SRS 3 FR-04: 승인 한도, 일일 한도, 위험 점수 기반 제어.
    """
    user_tier: str                  # basic, standard, premium, vip
    single_tx_limit: float          # 건당 한도
    daily_limit: float              # 일일 한도
    require_mfa_above: float        # 이 금액 이상 시 MFA 필요
    auto_approve_below: float       # 이 금액 이하 시 즉시 승인
    risk_score_threshold: float     # 위험 점수 임계값 (초과 시 에지 → 클라우드 에스컬레이션)


# 기본 UAC 정책 세트
DEFAULT_UAC_POLICIES: dict[str, UACPolicy] = {
    "basic": UACPolicy(
        user_tier="basic", single_tx_limit=500_000,
        daily_limit=2_000_000, require_mfa_above=300_000,
        auto_approve_below=50_000, risk_score_threshold=0.6,
    ),
    "standard": UACPolicy(
        user_tier="standard", single_tx_limit=2_000_000,
        daily_limit=10_000_000, require_mfa_above=1_000_000,
        auto_approve_below=200_000, risk_score_threshold=0.7,
    ),
    "premium": UACPolicy(
        user_tier="premium", single_tx_limit=10_000_000,
        daily_limit=50_000_000, require_mfa_above=5_000_000,
        auto_approve_below=500_000, risk_score_threshold=0.75,
    ),
    "vip": UACPolicy(
        user_tier="vip", single_tx_limit=50_000_000,
        daily_limit=200_000_000, require_mfa_above=20_000_000,
        auto_approve_below=2_000_000, risk_score_threshold=0.8,
    ),
}


# ── 거래 시뮬레이션 데이터 ────────────────────────────────────

@dataclass
class SimTransaction:
    """시뮬레이션 거래."""
    tx_id: str
    user_id: str
    user_tier: str
    amount: float
    risk_score: float               # 0.0 ~ 1.0
    region: str
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ApprovalResult:
    """거래 승인 결과."""
    tx_id: str
    decision: str                   # APPROVED, DENIED, ESCALATED, MFA_REQUIRED
    processing_node: str
    latency_ms: float
    reason: str
    escalated: bool = False


# ── MEC 거래 처리 엔진 ────────────────────────────────────────

class MECTransactionProcessor:
    """MEC 기반 실시간 거래 처리 시뮬레이터."""

    def __init__(
        self,
        mec_nodes: list[MECNode] | None = None,
        cloud: CloudNode | None = None,
        policies: dict[str, UACPolicy] | None = None,
    ) -> None:
        self.mec_nodes = mec_nodes or self._default_mec_nodes()
        self.cloud = cloud or CloudNode()
        self.policies = policies or DEFAULT_UAC_POLICIES

    def process_transaction(self, tx: SimTransaction) -> ApprovalResult:
        """거래를 처리하고 승인 결과를 반환."""
        policy = self.policies.get(tx.user_tier, self.policies["basic"])

        # 1) 에지 노드 선택
        edge = self._select_edge_node(tx.region)

        # 2) UAC 정책 평가
        if tx.amount > policy.single_tx_limit:
            return ApprovalResult(
                tx_id=tx.tx_id, decision="DENIED",
                processing_node=edge.node_id if edge else "cloud",
                latency_ms=edge.effective_latency_ms if edge else self.cloud.base_latency_ms,
                reason=f"건당 한도 초과: {tx.amount:,.0f} > {policy.single_tx_limit:,.0f}",
            )

        # 3) 자동 승인 (소액)
        if tx.amount <= policy.auto_approve_below and tx.risk_score < 0.3:
            latency = edge.effective_latency_ms if edge else self.cloud.base_latency_ms
            return ApprovalResult(
                tx_id=tx.tx_id, decision="APPROVED",
                processing_node=edge.node_id if edge else "cloud",
                latency_ms=latency + random.gauss(0, 2),
                reason="소액 자동 승인",
            )

        # 4) MFA 필요 여부
        if tx.amount >= policy.require_mfa_above:
            return ApprovalResult(
                tx_id=tx.tx_id, decision="MFA_REQUIRED",
                processing_node=edge.node_id if edge else "cloud",
                latency_ms=edge.effective_latency_ms if edge else self.cloud.base_latency_ms,
                reason=f"MFA 필요: 금액 {tx.amount:,.0f} >= {policy.require_mfa_above:,.0f}",
            )

        # 5) 위험 점수 기반 판정
        if tx.risk_score >= policy.risk_score_threshold:
            # 에지 → 클라우드 에스컬레이션
            cloud_latency = (
                self.cloud.base_latency_ms
                + random.gauss(0, self.cloud.network_jitter_ms)
            )
            total_latency = (
                (edge.effective_latency_ms if edge else 0) + cloud_latency
            )
            return ApprovalResult(
                tx_id=tx.tx_id, decision="ESCALATED",
                processing_node=f"{edge.node_id if edge else 'unknown'}→cloud",
                latency_ms=total_latency,
                reason=f"위험 점수 {tx.risk_score:.2f} >= 임계값 {policy.risk_score_threshold}",
                escalated=True,
            )

        # 6) 에지 승인
        latency = (edge.effective_latency_ms if edge else self.cloud.base_latency_ms) + random.gauss(0, 3)
        return ApprovalResult(
            tx_id=tx.tx_id, decision="APPROVED",
            processing_node=edge.node_id if edge else "cloud",
            latency_ms=max(1.0, latency),
            reason="에지 노드 승인",
        )

    def _select_edge_node(self, region: str) -> MECNode | None:
        """지역에 가장 적합한 에지 노드 선택."""
        candidates = [n for n in self.mec_nodes if n.region == region and n.is_active]
        if not candidates:
            # 가장 가까운 노드 선택 (부하가 가장 낮은 활성 노드)
            active = [n for n in self.mec_nodes if n.is_active]
            if not active:
                return None
            return min(active, key=lambda n: n.current_load)
        return min(candidates, key=lambda n: n.effective_latency_ms)

    def _default_mec_nodes(self) -> list[MECNode]:
        return [
            MECNode("mec-seoul-1", "seoul", 5.0, 1000, 0.3),
            MECNode("mec-seoul-2", "seoul", 6.0, 800, 0.5),
            MECNode("mec-busan-1", "busan", 7.0, 600, 0.2),
            MECNode("mec-daegu-1", "daegu", 8.0, 500, 0.15),
            MECNode("mec-gwangju-1", "gwangju", 9.0, 400, 0.1),
        ]


# ── 시뮬레이션 실행 ───────────────────────────────────────────

def generate_transactions(
    n: int = 1000,
    regions: list[str] | None = None,
    fraud_ratio: float = 0.03,
) -> list[SimTransaction]:
    """시뮬레이션용 거래 데이터를 생성."""
    regions = regions or ["seoul", "busan", "daegu", "gwangju", "seoul"]
    tiers = ["basic", "standard", "premium", "vip"]
    tier_weights = [0.4, 0.35, 0.2, 0.05]
    txns = []
    for i in range(n):
        tier = random.choices(tiers, weights=tier_weights, k=1)[0]
        is_fraud = random.random() < fraud_ratio
        amount = (
            random.lognormvariate(13, 2) if is_fraud
            else random.lognormvariate(11, 1.5)
        )
        risk_score = min(1.0, max(0.0,
            random.gauss(0.7, 0.15) if is_fraud else random.gauss(0.2, 0.15)
        ))
        txns.append(SimTransaction(
            tx_id=f"TX-{i:06d}",
            user_id=f"U-{random.randint(1, 200):04d}",
            user_tier=tier,
            amount=round(amount, 0),
            risk_score=round(risk_score, 4),
            region=random.choice(regions),
        ))
    return txns


def run_simulation(
    n_transactions: int = 1000,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """MEC vs Cloud 비교 시뮬레이션 실행.

    SRS 3 FR-04: 에지 노드 vs 중앙 클라우드 지연/처리량 비교.
    """
    processor = MECTransactionProcessor()
    cloud_only = MECTransactionProcessor(
        mec_nodes=[],
        cloud=CloudNode(base_latency_ms=150.0, network_jitter_ms=30.0),
    )

    txns = generate_transactions(n_transactions)

    # MEC 처리
    mec_results = [processor.process_transaction(tx) for tx in txns]
    # Cloud-only 처리
    cloud_results = [cloud_only.process_transaction(tx) for tx in txns]

    # 통계 집계
    mec_latencies = [r.latency_ms for r in mec_results]
    cloud_latencies = [r.latency_ms for r in cloud_results]

    def _decision_dist(results: list[ApprovalResult]) -> dict[str, int]:
        dist: dict[str, int] = {}
        for r in results:
            dist[r.decision] = dist.get(r.decision, 0) + 1
        return dist

    report = {
        "simulation": {
            "total_transactions": n_transactions,
            "mec_nodes": len(processor.mec_nodes),
        },
        "mec": {
            "avg_latency_ms": round(statistics.mean(mec_latencies), 2),
            "p50_latency_ms": round(statistics.median(mec_latencies), 2),
            "p95_latency_ms": round(sorted(mec_latencies)[int(0.95 * len(mec_latencies))], 2),
            "p99_latency_ms": round(sorted(mec_latencies)[int(0.99 * len(mec_latencies))], 2),
            "decision_distribution": _decision_dist(mec_results),
            "escalation_rate": round(
                sum(1 for r in mec_results if r.escalated) / len(mec_results), 4
            ),
        },
        "cloud": {
            "avg_latency_ms": round(statistics.mean(cloud_latencies), 2),
            "p50_latency_ms": round(statistics.median(cloud_latencies), 2),
            "p95_latency_ms": round(sorted(cloud_latencies)[int(0.95 * len(cloud_latencies))], 2),
            "p99_latency_ms": round(sorted(cloud_latencies)[int(0.99 * len(cloud_latencies))], 2),
            "decision_distribution": _decision_dist(cloud_results),
        },
        "comparison": {
            "latency_improvement_pct": round(
                (1 - statistics.mean(mec_latencies) / statistics.mean(cloud_latencies)) * 100, 1
            ),
            "mec_advantage": "MEC 에지 처리가 클라우드 대비 낮은 지연" if statistics.mean(mec_latencies) < statistics.mean(cloud_latencies) else "클라우드가 유리",
        },
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"결과 저장: {out}")

    return report


# ── CLI 실행 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    result = run_simulation(
        n_transactions=n,
        output_path="outputs/fds/mec_simulation_result.json",
    )
    print(f"\n=== MEC 시뮬레이션 결과 ({n}건) ===")
    print(f"MEC 평균 지연: {result['mec']['avg_latency_ms']:.1f}ms")
    print(f"Cloud 평균 지연: {result['cloud']['avg_latency_ms']:.1f}ms")
    print(f"지연 개선: {result['comparison']['latency_improvement_pct']}%")
    print(f"MEC 결정 분포: {result['mec']['decision_distribution']}")
    print(f"에스컬레이션 비율: {result['mec']['escalation_rate']:.1%}")
