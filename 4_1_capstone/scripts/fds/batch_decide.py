"""
스코어 CSV + 임계값 YAML → action(PASS|REVIEW|BLOCK), queue_priority.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FDS_DIR))
from policy_merge import decide_from_score  # noqa: E402


def load_thresholds(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    p = argparse.ArgumentParser(description="스코어에 정책 밴드 적용")
    p.add_argument("--scores", type=Path, required=True, help="batch_score.py 산출 CSV")
    p.add_argument("--policy", type=Path, default=Path("policies/fds/thresholds_v1.yaml"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    cfg = load_thresholds(args.policy)
    block_min = float(cfg["block_min"])
    review_min = float(cfg["review_min"])
    adjustments = cfg.get("adjustments", [])
    if not (0 <= review_min < block_min <= 1):
        raise ValueError("policy: 0 <= review_min < block_min <= 1 이어야 합니다 (검토 구간이 차단보다 낮음).")

    df = pd.read_csv(args.scores)
    if "score" not in df.columns:
        raise ValueError("scores CSV에 score 컬럼이 필요합니다.")

    # 원본 데이터 merge (변수 기반 조정용)
    if "transaction_id" in df.columns:
        # val.csv 경로 추정 (scores 파일명에서)
        val_path = args.scores.parent / args.scores.name.replace("scores_", "").replace("_fixed", "").replace("open_", "").replace(".csv", "").replace("val", "val.csv")
        if val_path.exists():
            val_df = pd.read_csv(val_path)
            val_df = val_df.rename(columns={"ID": "transaction_id"})
            df = df.merge(val_df, on="transaction_id", how="left")

    actions = []
    for _, row in df.iterrows():
        score = float(row["score"])
        action = decide_from_score(score, block_min, review_min, adjustments, row.to_dict() if adjustments else None)
        actions.append(action)
    out = df.copy()
    out["action"] = actions
    out["queue_priority"] = out["score"].astype(float)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    vc = out["action"].value_counts()
    print(f"저장: {args.output}")
    print(vc.to_string())


if __name__ == "__main__":
    main()
