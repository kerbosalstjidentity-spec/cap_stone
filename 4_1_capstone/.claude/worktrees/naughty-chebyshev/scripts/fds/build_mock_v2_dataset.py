"""
모의 스키마 v2용 CSV 생성.

- 기본: 합성 V1–V30 + ID + channel + country_txn + Class (val 없이 재현 가능)
- --from-val: data/open/val.csv 상위 n행에 메타 컬럼만 부여 (로컬에 val 있을 때)
- --fraud-rate: 사기 비율 (기본 0.002). 현실적 패턴은 --realistic 플래그로 활성화.

현실적 패턴 (--realistic):
  실제 creditcard 데이터 분포에 근거하여 사기 거래의 주요 피처를 이동.
  V14, V12, V10, V11: 사기 시 음수 방향 이동 (실제 데이터 통계 기반)
  V4, V2: 사기 시 양수 방향 이동
  amount: 사기 거래가 정상보다 약간 높은 금액 분포
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

# 실제 creditcard.csv 통계에서 추출한 사기 피처 평균 이동량
# (정상=0 기준 상대 이동)
_FRAUD_SHIFTS = {
    "V14": -4.8,
    "V12": -3.9,
    "V10": -2.5,
    "V11": -3.2,
    "V4":  +3.1,
    "V2":  +2.4,
    "V17": -3.5,
    "V16": -2.1,
}


def synthetic(n: int, seed: int, fraud_rate: float = 0.002, realistic: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    feat = [f"V{i}" for i in range(1, 31)]
    X = rng.standard_normal((n, 30))
    df = pd.DataFrame(X, columns=feat)
    df.insert(0, "ID", [f"MOCK_{i:06d}" for i in range(n)])

    fraud = rng.random(n) < fraud_rate

    # 현실적 패턴: 사기 거래의 주요 피처 이동
    if realistic and fraud.sum() > 0:
        fidx = np.where(fraud)[0]
        for feat_name, shift in _FRAUD_SHIFTS.items():
            col_idx = int(feat_name[1:]) - 1  # V14 → index 13
            if 0 <= col_idx < 30:
                X[fidx, col_idx] += shift + rng.standard_normal(len(fidx)) * 0.5
        df = pd.DataFrame(X, columns=feat)
        df.insert(0, "ID", [f"MOCK_{i:06d}" for i in range(n)])

    df["Class"] = fraud.astype(int)

    # amount: 정상 거래 로그정규, 사기 거래는 약간 높음
    normal_amount = np.exp(rng.normal(3.5, 1.2, n))  # 평균 약 33
    if realistic:
        fraud_amount = np.exp(rng.normal(4.2, 1.1, n))  # 평균 약 66
        df["amount"] = np.where(fraud, fraud_amount, normal_amount).round(2)
    else:
        df["amount"] = normal_amount.round(2)

    ch = rng.choice(["online", "offline", "app"], size=n)
    # 일부 행에 규칙 테스트용 국가 코드
    co = rng.choice(["KR", "US", "JP", "HIGH_RISK", "XX"], size=n, p=[0.45, 0.25, 0.2, 0.05, 0.05])
    df["channel"] = ch
    df["country_txn"] = co

    # user_id: USR_001 ~ USR_050 (50명, 일부 사용자가 여러 거래)
    user_ids = [f"USR_{i:03d}" for i in range(1, 51)]
    df["user_id"] = rng.choice(user_ids, size=n)

    # event_ts: 2025-01-01 ~ 2025-03-31 범위 (더 넓은 범위)
    start_ts = pd.Timestamp("2025-01-01").value
    end_ts = pd.Timestamp("2025-03-31 23:59:59").value
    random_ts = rng.integers(start_ts, end_ts, size=n)
    df["event_ts"] = pd.to_datetime(random_ts).strftime("%Y-%m-%dT%H:%M:%S")

    # merchant_id: MCH_01 ~ MCH_20 (20개 가맹점)
    merchant_ids = [f"MCH_{i:02d}" for i in range(1, 21)]
    df["merchant_id"] = rng.choice(merchant_ids, size=n)

    return df


def from_val(path: Path, n: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(path, nrows=n)
    rng = np.random.default_rng(seed)
    df["channel"] = rng.choice(["online", "offline", "app"], size=len(df))
    df["country_txn"] = rng.choice(["KR", "US", "JP", "HIGH_RISK", "XX"], size=len(df), p=[0.45, 0.25, 0.2, 0.05, 0.05])

    # user_id: USR_001 ~ USR_050
    user_ids = [f"USR_{i:03d}" for i in range(1, 51)]
    df["user_id"] = rng.choice(user_ids, size=len(df))

    # event_ts: 2025-01-01 ~ 2025-01-31 범위의 랜덤 datetime (ISO 형식)
    start_ts = pd.Timestamp("2025-01-01").value
    end_ts = pd.Timestamp("2025-01-31 23:59:59").value
    random_ts = rng.integers(start_ts, end_ts, size=len(df))
    df["event_ts"] = pd.to_datetime(random_ts).strftime("%Y-%m-%dT%H:%M:%S")

    # merchant_id: MCH_01 ~ MCH_20
    merchant_ids = [f"MCH_{i:02d}" for i in range(1, 21)]
    df["merchant_id"] = rng.choice(merchant_ids, size=len(df))

    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "data" / "fds" / "mock_transactions_v2.csv")
    p.add_argument("--nrows", type=int, default=500)
    p.add_argument("--fraud-rate", type=float, default=0.002, help="사기 비율 (기본 0.002 = 0.2%%)")
    p.add_argument("--realistic", action="store_true", help="사기 거래에 현실적 피처 이동 적용")
    p.add_argument("--from-val", action="store_true")
    p.add_argument("--val-csv", type=Path, default=ROOT / "data" / "open" / "val.csv")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if args.from_val:
        if not args.val_csv.exists():
            raise SystemExit(f"없음: {args.val_csv} (--from-val 해제 시 합성 데이터 생성)")
        df = from_val(args.val_csv, args.nrows, args.seed)
    else:
        df = synthetic(args.nrows, args.seed, fraud_rate=args.fraud_rate, realistic=args.realistic)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"저장: {args.out}  행: {len(df):,}  열: {list(df.columns)}")


if __name__ == "__main__":
    main()
