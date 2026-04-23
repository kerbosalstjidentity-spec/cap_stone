"""
배치 스코어링: CSV 입력 → transaction_id, score(사기 확률), reason_code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FDS_DIR))

from scoring import score_prepared_frame  # noqa: E402
from schema import FDSSchema  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="FDS 배치 스코어링")
    p.add_argument("--bundle", type=Path, required=True, help="train_export_rf.py 산출 joblib")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--top-reasons", type=int, default=3)
    p.add_argument("--nrows", type=int, default=None, help="입력 상위 n행만 스코어 (스모크용)")
    args = p.parse_args()

    bundle = joblib.load(args.bundle)
    schema = FDSSchema.from_dict(bundle["schema_raw"])

    df = pd.read_csv(args.input, nrows=args.nrows)
    df = schema.prepare_frame(df)
    out = score_prepared_frame(df, bundle, top_reasons=args.top_reasons)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"스코어 저장: {args.output}  행: {len(out):,}")


if __name__ == "__main__":
    main()
