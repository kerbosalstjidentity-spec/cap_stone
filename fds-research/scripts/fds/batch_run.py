"""
규칙 → 모델 스코어 → 임계값 밴드 → 최종 조치(합성) 한 번에 실행.
산출: 감사용 컬럼(model_score, rule_ids, model_action, final_action, audit_summary 등).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from policy_merge import audit_summary, decide_from_score, merge_actions  # noqa: E402
from rules_engine import evaluate_rules  # noqa: E402
from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402


def load_thresholds(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    p = argparse.ArgumentParser(description="FDS 통합 배치: 규칙+모델+임계값")
    p.add_argument("--schema", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--rules", type=Path, default=Path("policies/fds/rules_v1.yaml"))
    p.add_argument("--thresholds", type=Path, default=Path("policies/fds/thresholds_v1.yaml"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--nrows", type=int, default=None)
    p.add_argument("--top-reasons", type=int, default=3)
    args = p.parse_args()

    schema = FDSSchema.from_yaml(args.schema)
    bundle = joblib.load(args.bundle)
    th = load_thresholds(args.thresholds)
    block_min = float(th["block_min"])
    review_min = float(th["review_min"])
    if not (0 <= review_min < block_min <= 1):
        raise ValueError("thresholds: 0 <= review_min < block_min <= 1")

    df = pd.read_csv(args.input, nrows=args.nrows)
    df = schema.prepare_frame(df)

    rule_df = evaluate_rules(df, args.rules, PROJECT_ROOT)
    scored = score_prepared_frame(df, bundle, top_reasons=args.top_reasons)

    model_actions = [
        decide_from_score(float(s), block_min, review_min) for s in scored["score"]
    ]
    final_actions = [
        merge_actions(ra, ma) for ra, ma in zip(rule_df["rule_action"], model_actions)
    ]
    audits = [
        audit_summary(rc, rid)
        for rc, rid in zip(scored["reason_code"], rule_df["rule_ids"])
    ]

    out = pd.DataFrame(
        {
            "transaction_id": scored["transaction_id"],
            "model_score": scored["score"],
            "reason_code": scored["reason_code"],
            "rule_ids": rule_df["rule_ids"].values,
            "rule_action": rule_df["rule_action"].values,
            "model_action": model_actions,
            "final_action": final_actions,
            "queue_priority": scored["score"].astype(float),
            "audit_summary": audits,
        }
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"저장: {args.output}  행: {len(out):,}")
    print(out["final_action"].value_counts().to_string())


if __name__ == "__main__":
    main()
