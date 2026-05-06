"""W6.5-#7 보조 — 그래프 시드의 BLOCK 승격 기여도 마이크로 벤치.

회귀 테스트(``tests/test_w65_integrated_regression.py``) 는 graph-seeded
조건 하 ≥90% 강건만 보장한다. baseline(그래프 비어) vs graph-aware 정량
비교는 비용 임계값(W6.5-#5) 단독으로 큰 amount 구간이 saturation 되므로
저금액 sweep 으로만 의미 있는 uplift 가 관측된다.

실행:
    cd fraud-service
    python -m scripts.bench_w65_graph_uplift

출력: amount × graph 컨텍스트 → BLOCK / REVIEW / PASS 분포 표.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

# fraud-service 루트를 sys.path 에 추가 — `python -m scripts.X` 외 직접 실행도 허용
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENV", "development")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.middleware import rate_limit  # noqa: E402
from app.services.graph_store import graph_store  # noqa: E402
from app.services.scenario_generator import generate  # noqa: E402

rate_limit._ENABLED = False  # 200req+ 회피
client = TestClient(app)

EXIT_NODES = ["exit_a_bench", "exit_b_bench", "exit_c_bench"]
BASELINE_VICTIMS = [f"victim_b_{i}" for i in range(6)]
SEEDED_VICTIMS = [f"victim_s_{i}" for i in range(6)]


def _seed_hub(mule_ids: list[str], victims: list[str]) -> None:
    for m in mule_ids:
        for v in victims:
            graph_store.record(v, m, 1000.0)
        for ex in EXIT_NODES:
            graph_store.record(m, ex, 1500.0)


def _clear(nodes: list[str]) -> None:
    graph_store.clear(nodes=nodes)


def _run(amount: float, *, seeded: bool) -> Counter:
    prefix = "mule_seed_" if seeded else "mule_alt_"
    mule_ids = [f"{prefix}{i}" for i in range(5)]
    if seeded:
        _seed_hub(mule_ids, SEEDED_VICTIMS)
    txs = generate("MONEY_MULE", count=100, seed=42, user_id_prefix=prefix)
    actions: Counter = Counter()
    for tx in txs:
        payload = {
            "tx_id": f"{tx['tx_id']}-{int(amount)}-{'S' if seeded else 'B'}",
            "score": 0.45,
            "amount": amount,
            "user_id": tx["user_id"],
            "receiver_id": EXIT_NODES[0],
        }
        r = client.post("/v1/fraud/evaluate", json=payload)
        r.raise_for_status()
        actions[r.json()["final_action"]] += 1
    _clear(mule_ids + EXIT_NODES + (SEEDED_VICTIMS if seeded else []))
    return actions


def main() -> int:
    amounts = [50_000.0, 100_000.0, 500_000.0, 2_000_000.0]
    print(f"\n{'amount':>12} | {'context':<10} | {'BLOCK':>6} {'REVIEW':>6} {'SOFT':>6} {'PASS':>6}")
    print("-" * 64)
    for amt in amounts:
        for seeded in (False, True):
            ctx = "seeded" if seeded else "baseline"
            a = _run(amt, seeded=seeded)
            print(
                f"{int(amt):>12,} | {ctx:<10} | "
                f"{a.get('BLOCK', 0):>6} {a.get('REVIEW', 0):>6} "
                f"{a.get('SOFT_REVIEW', 0):>6} {a.get('PASS', 0):>6}"
            )
        print("-" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
