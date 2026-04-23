"""
배치 산출물 요약: 점수 분포, 조치 비율, (옵션) 라벨이 있으면 큐 품질 지표.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="FDS 모니터링 요약")
    p.add_argument("--decisions", type=Path, help="batch_run / batch_decide CSV")
    p.add_argument("--scores", type=Path, help="batch_score 전용 CSV (score만)")
    p.add_argument("--label-col", type=str, default=None, help="예: is_fraud, Class (같은 CSV에 있을 때)")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()

    if args.decisions:
        df = pd.read_csv(args.decisions, low_memory=False)
    elif args.scores:
        df = pd.read_csv(args.scores, low_memory=False)
    else:
        raise SystemExit("--decisions 또는 --scores 중 하나는 필요합니다.")

    score_col = "model_score" if "model_score" in df.columns else "score"
    if score_col not in df.columns:
        raise ValueError("model_score 또는 score 컬럼이 필요합니다.")

    s = pd.to_numeric(df[score_col], errors="coerce")
    summary: dict = {
        "rows": int(len(df)),
        "score_quantiles": {
            "p50": float(s.median()),
            "p90": float(s.quantile(0.9)),
            "p99": float(s.quantile(0.99)),
        },
        "score_mean": float(s.mean()),
        "score_std": float(s.std(ddof=0)),
    }

    act_col = None
    for c in ("final_action", "action"):
        if c in df.columns:
            act_col = c
            break
    if act_col:
        vc = df[act_col].value_counts(normalize=True)
        summary["action_rate"] = {str(k): float(v) for k, v in vc.items()}
        summary["approval_proxy_pass_rate"] = float((df[act_col] == "PASS").mean())

    if args.label_col and args.label_col in df.columns:
        y = pd.to_numeric(df[args.label_col], errors="coerce").fillna(0).astype(int)
        summary["label_fraud_rate"] = float(y.mean())
        if act_col:
            flagged = df[act_col].isin(["REVIEW", "BLOCK"])
            if flagged.any():
                summary["fraud_rate_in_review_or_block"] = float(y[flagged].mean())
                tp = int(((flagged) & (y == 1)).sum())
                fp = int(((flagged) & (y == 0)).sum())
                fn = int(((~flagged) & (y == 1)).sum())
                summary["queue_tp"] = tp
                summary["queue_fp"] = fp
                summary["queue_fn_outside_queue"] = fn

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON 저장: {args.json_out}")


if __name__ == "__main__":
    main()
