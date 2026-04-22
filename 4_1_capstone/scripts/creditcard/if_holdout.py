# /* ============================================================================
#  * creditcard/if_holdout.py — Kaggle creditcard 비지도(경량)
#  * Isolation Forest: stratified 홀드아웃 + contamination 스윕 +
#  *   고정 학습 후 score_samples로 하위 k% 임계값 실험
#  * ========================================================================== */

import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
TEST_SIZE = 0.25
ISOLATION_N_ESTIMATORS = 100


def add_scaled_amount_time(df: pd.DataFrame, scaler_amount: RobustScaler, scaler_time: RobustScaler) -> pd.DataFrame:
    out = df.copy()
    out["scaled_amount"] = scaler_amount.transform(out["Amount"].values.reshape(-1, 1))
    out["scaled_time"] = scaler_time.transform(out["Time"].values.reshape(-1, 1))
    return out


def build_x(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(["Time", "Amount", "Class"], axis=1)


def metrics_from_mask(y_true, pred_anomaly) -> tuple[int, int, int, int]:
    fraud = y_true == 1
    normal = y_true == 0
    tp = int((pred_anomaly & fraud).sum())
    fp = int((pred_anomaly & normal).sum())
    fn = int((~pred_anomaly & fraud).sum())
    tn = int((~pred_anomaly & normal).sum())
    return tp, fp, fn, tn


def print_metrics_block(title: str, y_test, pred_anomaly) -> None:
    tp, fp, fn, tn = metrics_from_mask(y_test, pred_anomaly)
    n_fraud = int((y_test == 1).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / n_fraud if n_fraud else 0.0
    print(f"\n=== {title} ===")
    print(f"TP={tp:,}  FP={fp:,}  FN={fn:,}  TN={tn:,}")
    print(f"Precision(의심 중 실제 사기): {prec:.4f}  |  Recall(사기 중 의심): {rec:.4f}")


def main() -> None:
    df = pd.read_csv(PROJECT_ROOT / "data" / "creditcard.csv")

    train_df, test_df = train_test_split(
        df,
        test_size=TEST_SIZE,
        stratify=df["Class"],
        random_state=RANDOM_STATE,
    )

    scaler_amount = RobustScaler()
    scaler_time = RobustScaler()
    scaler_amount.fit(train_df["Amount"].values.reshape(-1, 1))
    scaler_time.fit(train_df["Time"].values.reshape(-1, 1))

    train_df = add_scaled_amount_time(train_df, scaler_amount, scaler_time)
    test_df = add_scaled_amount_time(test_df, scaler_amount, scaler_time)

    X_train = build_x(train_df)
    X_test = build_x(test_df)
    y_test = test_df["Class"].values

    contaminations = [0.0005, 0.001, 0.0017, 0.005, 0.01, 0.02]
    print("=" * 72)
    print("Part A — contamination 스윕 (train fit / test 평가, Class는 평가용만)")
    print("=" * 72)

    for contam in contaminations:
        model = IsolationForest(
            n_estimators=ISOLATION_N_ESTIMATORS,
            contamination=contam,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(X_train)
        pred = model.predict(X_test)
        pred_anomaly = pred == -1
        print_metrics_block(f"contamination={contam}", y_test, pred_anomaly)

    ref_model = IsolationForest(
        n_estimators=ISOLATION_N_ESTIMATORS,
        contamination=0.01,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    ref_model.fit(X_train)
    scores = ref_model.score_samples(X_test)

    print("\n" + "=" * 72)
    print("Part B — score_samples: 낮은 점수 순으로 하위 k%를 이상으로 간주")
    print("=" * 72)

    score_series = pd.Series(scores)
    for pct in [0.05, 0.1, 0.17, 0.5, 1.0, 2.0]:
        thresh = score_series.quantile(pct / 100.0)
        pred_anomaly = (score_series <= thresh).values
        print_metrics_block(f"하위 {pct}% (score <= {pct}th percentile)", y_test, pred_anomaly)

    print("\n(끝) 테스트 행 수:", f"{len(y_test):,}", "  사기 건수:", f"{(y_test == 1).sum():,}")


if __name__ == "__main__":
    main()
