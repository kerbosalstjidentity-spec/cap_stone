"""creditcard 데이터에 Isolation Forest 한 번 학습·요약하는 짧은 데모."""
import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    df = pd.read_csv(PROJECT_ROOT / "data" / "creditcard.csv")

    scaler = RobustScaler()
    df["scaled_amount"] = scaler.fit_transform(df["Amount"].values.reshape(-1, 1))
    df["scaled_time"] = scaler.fit_transform(df["Time"].values.reshape(-1, 1))

    X = df.drop(["Time", "Amount", "Class"], axis=1)

    model = IsolationForest(n_estimators=100, contamination=0.0017, random_state=42)

    model.fit(X)
    df["prediction"] = model.predict(X)

    anomaly = df["prediction"] == -1
    fraud = df["Class"] == 1
    n = len(df)
    print(f"전체 행: {n:,}")
    print(f"모델이 이상(-1)으로 분류: {anomaly.sum():,} ({100 * anomaly.mean():.4f}%)")
    print(f"실제 사기(Class=1): {fraud.sum():,}")
    if fraud.any():
        tp = (anomaly & fraud).sum()
        print(f"사기 중 이상으로 겹침: {tp:,} / {fraud.sum():,} (라벨 대비 참고)")
    print(f"정상(Class=0)인데 이상으로 분류: {(anomaly & ~fraud).sum():,}")
    print("\nprediction 분포:\n", df["prediction"].value_counts().to_string())


if __name__ == "__main__":
    main()
