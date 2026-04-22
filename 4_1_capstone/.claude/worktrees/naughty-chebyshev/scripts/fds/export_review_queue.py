"""
final_action == REVIEW (또는 옵션으로 BLOCK) 만 추출, queue_priority 내림차순.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _maybe_hash(s: str, enabled: bool, n: int = 16) -> str:
    if not enabled:
        return s
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return h[:n]


def main() -> None:
    p = argparse.ArgumentParser(description="검토 큐 CSV 추출")
    p.add_argument("--decisions", type=Path, required=True, help="batch_run 또는 batch_decide 산출")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--include-block", action="store_true", help="BLOCK 도 큐 파일에 포함 (사후 감사용)")
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--hash-id", action="store_true", help="transaction_id SHA256 앞 16자 (로그 PII 완화)")
    args = p.parse_args()

    df = pd.read_csv(args.decisions, low_memory=False)
    col_action = "final_action" if "final_action" in df.columns else "action"
    if col_action not in df.columns:
        raise ValueError("final_action 또는 action 컬럼이 필요합니다.")

    m = df[col_action] == "REVIEW"
    if args.include_block:
        m = m | (df[col_action] == "BLOCK")

    q = df.loc[m].copy()
    prio_col = "queue_priority" if "queue_priority" in q.columns else "model_score"
    if prio_col not in q.columns and "score" in q.columns:
        prio_col = "score"
    if prio_col not in q.columns:
        raise ValueError("queue_priority, model_score, score 중 하나가 필요합니다.")

    q = q.sort_values(prio_col, ascending=False, kind="mergesort")
    if args.max_rows is not None:
        q = q.head(args.max_rows)

    id_col = "transaction_id"
    if id_col in q.columns and args.hash_id:
        q[id_col] = q[id_col].astype(str).map(lambda x: _maybe_hash(x, True))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    q.to_csv(args.output, index=False)
    print(f"검토 큐 저장: {args.output}  행: {len(q):,}")


if __name__ == "__main__":
    main()
