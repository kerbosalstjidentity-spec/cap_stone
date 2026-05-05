"""PaySim 데이터셋 로더 (W5.5-#2).

Kaggle ealaxi/paysim1 의 ``PS_*_log.csv`` 또는 ``paysim.csv`` 를 로드해
표준 컬럼·dtype 으로 정규화한다. 도메인 매핑은 FDS_ROADMAP §PaySim 참조.

사용:
    from scripts.paysim.load import load_paysim
    df = load_paysim()                          # default fds-research/data/paysim.csv
    df = load_paysim(types=("TRANSFER", "CASH_OUT"))  # 사기 발생 타입만
    df = load_paysim(sample=100_000, seed=42)   # 부분 샘플
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "paysim.csv"

REQUIRED_COLUMNS: tuple[str, ...] = (
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
)

DTYPES = {
    "step": "int32",
    "type": "category",
    "amount": "float64",
    "nameOrig": "string",
    "oldbalanceOrg": "float64",
    "newbalanceOrig": "float64",
    "nameDest": "string",
    "oldbalanceDest": "float64",
    "newbalanceDest": "float64",
    "isFraud": "int8",
    "isFlaggedFraud": "int8",
}


def resolve_path(path: str | os.PathLike | None = None) -> Path:
    """``PAYSIM_PATH`` env > 인자 > 기본 경로 순서로 해석."""
    env = os.environ.get("PAYSIM_PATH")
    if path is not None:
        return Path(path)
    if env:
        return Path(env)
    return DEFAULT_PATH


def load_paysim(
    path: str | os.PathLike | None = None,
    *,
    types: Iterable[str] | None = None,
    sample: int | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """PaySim CSV 를 표준 dtype 으로 로드.

    Args:
        path: 명시 경로 (없으면 ``PAYSIM_PATH`` env, 그것도 없으면 기본 경로).
        types: 필터할 거래 타입 (예: ``("TRANSFER", "CASH_OUT")``). None=전체.
        sample: 행 수 제한 (학습 디버깅용). 사기는 그대로 보존하고 비사기에서 다운샘플.
        seed: 샘플링 시드.
    """
    csv_path = resolve_path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"PaySim CSV not found at {csv_path}. "
            f"Run `make paysim-download` or place the file there manually."
        )

    df = pd.read_csv(csv_path, dtype=DTYPES)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"PaySim CSV missing columns: {missing}")

    if types:
        df = df[df["type"].isin(list(types))].reset_index(drop=True)

    if sample is not None and sample < len(df):
        # 사기는 보존, 정상에서만 다운샘플 (불균형 데이터 검토 편의)
        fraud = df[df["isFraud"] == 1]
        normal = df[df["isFraud"] == 0]
        keep_normal = max(0, sample - len(fraud))
        if keep_normal < len(normal):
            normal = normal.sample(n=keep_normal, random_state=seed)
        df = pd.concat([fraud, normal], ignore_index=True).sample(
            frac=1.0, random_state=seed
        ).reset_index(drop=True)

    return df


def summary(df: pd.DataFrame) -> dict:
    """간단한 통계. 검증 스크립트에서 출력용."""
    return {
        "rows": int(len(df)),
        "fraud_rows": int(df["isFraud"].sum()),
        "fraud_rate": float(df["isFraud"].mean()),
        "type_counts": {k: int(v) for k, v in df["type"].value_counts().to_dict().items()},
        "fraud_by_type": {
            k: int(v) for k, v in df.groupby("type", observed=True)["isFraud"].sum().to_dict().items()
        },
        "amount": {
            "min": float(df["amount"].min()),
            "mean": float(df["amount"].mean()),
            "max": float(df["amount"].max()),
        },
        "step_range": [int(df["step"].min()), int(df["step"].max())],
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Inspect PaySim CSV stats")
    ap.add_argument("--path", default=None, help="CSV 경로 override")
    ap.add_argument("--types", nargs="*", default=None, help="필터 타입")
    ap.add_argument("--sample", type=int, default=None, help="샘플 수")
    args = ap.parse_args()

    df = load_paysim(path=args.path, types=args.types, sample=args.sample)
    print(json.dumps(summary(df), indent=2, ensure_ascii=False))
