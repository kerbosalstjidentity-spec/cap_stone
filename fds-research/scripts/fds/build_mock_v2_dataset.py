"""
모의 스키마 v2용 CSV 생성.

- 기본: 합성 V1–V30 + ID + channel + country_txn + Class (val 없이 재현 가능)
- --from-val: data/open/val.csv 상위 n행에 메타 컬럼만 부여 (로컬에 val 있을 때)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]


def synthetic(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    feat = [f"V{i}" for i in range(1, 31)]
    X = rng.standard_normal((n, 30))
    df = pd.DataFrame(X, columns=feat)
    df.insert(0, "ID", [f"MOCK_{i:06d}" for i in range(n)])
    fraud = rng.random(n) < 0.002
    df["Class"] = fraud.astype(int)
    ch = rng.choice(["online", "offline", "app"], size=n)
    # 일부 행에 규칙 테스트용 국가 코드
    co = rng.choice(["KR", "US", "JP", "HIGH_RISK", "XX"], size=n, p=[0.45, 0.25, 0.2, 0.05, 0.05])
    df["channel"] = ch
    df["country_txn"] = co
    return df


def from_val(path: Path, n: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(path, nrows=n)
    rng = np.random.default_rng(seed)
    df["channel"] = rng.choice(["online", "offline", "app"], size=len(df))
    df["country_txn"] = rng.choice(["KR", "US", "JP", "HIGH_RISK", "XX"], size=len(df), p=[0.45, 0.25, 0.2, 0.05, 0.05])
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "data" / "fds" / "mock_transactions_v2.csv")
    p.add_argument("--nrows", type=int, default=500)
    p.add_argument("--from-val", action="store_true")
    p.add_argument("--val-csv", type=Path, default=ROOT / "data" / "open" / "val.csv")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if args.from_val:
        if not args.val_csv.exists():
            raise SystemExit(f"없음: {args.val_csv} (--from-val 해제 시 합성 데이터 생성)")
        df = from_val(args.val_csv, args.nrows, args.seed)
    else:
        df = synthetic(args.nrows, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"저장: {args.out}  행: {len(df):,}  열: {list(df.columns)}")


if __name__ == "__main__":
    main()
