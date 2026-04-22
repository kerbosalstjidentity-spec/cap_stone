"""
스코어 CSV + 임계값 YAML → action(PASS|REVIEW|BLOCK), queue_priority.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import yaml

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FDS_DIR))
from policy_merge import decide_from_score  # noqa: E402

logger = logging.getLogger(__name__)


def load_thresholds(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    p = argparse.ArgumentParser(description="스코어에 정책 밴드 적용")
    p.add_argument("--scores", type=Path, required=True, help="batch_score.py 산출 CSV")
    p.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "policies" / "fds" / "thresholds_v1.yaml",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help=(
            "변수 기반 조정(adjustments)에 사용할 원본 데이터 CSV. "
            "지정하면 transaction_id 기준으로 merge하여 V1–V30 등 특성을 조정 조건에 활용한다. "
            "미지정 시 변수 기반 조정이 비활성화된다."
        ),
    )
    args = p.parse_args()

    cfg = load_thresholds(args.policy)
    block_min = float(cfg["block_min"])
    review_min = float(cfg["review_min"])
    adjustments = cfg.get("adjustments", [])
    if not (0 <= review_min < block_min <= 1):
        raise ValueError("policy: 0 <= review_min < block_min <= 1 이어야 합니다.")

    df = pd.read_csv(args.scores)
    if "score" not in df.columns:
        raise ValueError("scores CSV에 score 컬럼이 필요합니다.")

    # 변수 기반 조정: 명시적 --input-csv 경로만 허용 (경로 추정 제거)
    if adjustments and args.input_csv:
        if not args.input_csv.exists():
            logger.warning("--input-csv 경로를 찾을 수 없음: %s — 변수 기반 조정 비활성화", args.input_csv)
            adjustments = []
        else:
            input_df = pd.read_csv(args.input_csv)
            id_col = "transaction_id" if "transaction_id" in input_df.columns else (
                "ID" if "ID" in input_df.columns else None
            )
            if id_col and "transaction_id" in df.columns:
                input_df = input_df.rename(columns={id_col: "transaction_id"})
                df = df.merge(input_df, on="transaction_id", how="left", suffixes=("", "_orig"))
            else:
                logger.warning("transaction_id 컬럼 불일치 — 변수 기반 조정 비활성화")
                adjustments = []
    elif adjustments and not args.input_csv:
        msg = (
            "[경고] adjustments가 정의되어 있으나 --input-csv 미지정 — "
            "변수 기반 조정이 비활성화됩니다. "
            "조정을 적용하려면 --input-csv <원본 데이터 CSV>를 전달하세요."
        )
        logger.warning(msg)
        print(msg, file=sys.stderr)
        adjustments = []

    actions = []
    for _, row in df.iterrows():
        score = float(row["score"])
        action = decide_from_score(
            score, block_min, review_min,
            adjustments if adjustments else None,
            row.to_dict() if adjustments else None,
        )
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
