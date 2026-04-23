# /* ============================================================================
#  * creditcard/if_unsupervised.py — Kaggle creditcard 비지도(전체 실험)
#  *  - stratified 홀드아웃, train-only 스케일링, IF + contamination / score_samples
#  *  - FPR, 요약 CSV, '검토 상한 K건' 실험(상위 의심)
#  * ========================================================================== */

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# /* ---------------------------------------------------------------------------
#  * 실험 설정 (보고서·재현용으로 한곳에 모음)
#  * -------------------------------------------------------------------------- */
RANDOM_STATE = 42
TEST_SIZE = 0.25
ISOLATION_N_ESTIMATORS = 100
PART_B_REF_CONTAMINATION = 0.01


CONTAMINATIONS = [0.0005, 0.001, 0.0017, 0.005, 0.01, 0.02]
PERCENTILE_KS = [0.05, 0.1, 0.17, 0.5, 1.0, 2.0]
# '하루 검토 가능 건수' 가정에 가깝게: 점수가 가장 나쁜(가장 이상) 순으로 K건만 의심
TOP_K_ALERTS = [35, 50, 100, 200, 500]


def add_scaled_amount_time(
    df: pd.DataFrame, scaler_amount: RobustScaler, scaler_time: RobustScaler
) -> pd.DataFrame:
    out = df.copy()
    out["scaled_amount"] = scaler_amount.transform(out["Amount"].values.reshape(-1, 1))
    out["scaled_time"] = scaler_time.transform(out["Time"].values.reshape(-1, 1))
    return out


def build_x(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(["Time", "Amount", "Class"], axis=1)


def confusion_and_rates(y_true, pred_anomaly) -> dict:
    """
    pred_anomaly=True 를 '의심(양성)'으로 둠.
    FPR(정상 중 오탐률) = FP / (정상 수) — 정상만 볼 때 의심으로 잘못 찍힌 비율.
    """
    y_true = pd.Series(y_true).astype(int)
    fraud = y_true == 1
    normal = y_true == 0
    tp = int((pred_anomaly & fraud).sum())
    fp = int((pred_anomaly & normal).sum())
    fn = int((~pred_anomaly & fraud).sum())
    tn = int((~pred_anomaly & normal).sum())
    n_fraud = int(fraud.sum())
    n_normal = int(normal.sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / n_fraud if n_fraud else 0.0
    fpr_normal = fp / n_normal if n_normal else 0.0
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "Precision": round(prec, 4),
        "Recall": round(rec, 4),
        "FPR_normal": round(fpr_normal, 6),
    }


def print_block(title: str, row: dict) -> None:
    print(f"\n=== {title} ===")
    print(
        f"TP={row['TP']:,}  FP={row['FP']:,}  FN={row['FN']:,}  TN={row['TN']:,}"
    )
    print(
        f"Precision: {row['Precision']:.4f}  |  Recall: {row['Recall']:.4f}  |  "
        f"FPR(정상 중 오탐): {row['FPR_normal']:.6f}"
    )


def main() -> None:
    csv_path = PROJECT_ROOT / "data" / "creditcard.csv"
    df = pd.read_csv(csv_path)

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
    n_test = len(y_test)
    n_fraud_test = int((y_test == 1).sum())

    rows: list[dict] = []

    # /* Part A — contamination */
    print("=" * 72)
    print("Part A — contamination 스윕 (train fit / test 평가)")
    print("=" * 72)

    for contam in CONTAMINATIONS:
        model = IsolationForest(
            n_estimators=ISOLATION_N_ESTIMATORS,
            contamination=contam,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(X_train)
        pred_anomaly = model.predict(X_test) == -1
        r = confusion_and_rates(y_test, pred_anomaly)
        label = f"A_contam_{contam}"
        print_block(f"contamination={contam}", r)
        rows.append({"experiment": label, "setting": str(contam), **r})

    # /* Part B — score_samples + 하위 k% */
    ref_model = IsolationForest(
        n_estimators=ISOLATION_N_ESTIMATORS,
        contamination=PART_B_REF_CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    ref_model.fit(X_train)
    scores = ref_model.score_samples(X_test)
    score_series = pd.Series(scores, index=test_df.index)

    print("\n" + "=" * 72)
    print("Part B — score_samples: 하위 k% 를 의심 (ref contamination=" f"{PART_B_REF_CONTAMINATION})")
    print("=" * 72)

    for pct in PERCENTILE_KS:
        thresh = score_series.quantile(pct / 100.0)
        pred_anomaly = (score_series <= thresh).values
        r = confusion_and_rates(y_test, pred_anomaly)
        label = f"B_pct_{pct}"
        print_block(f"하위 {pct}%", r)
        rows.append({"experiment": label, "setting": f"p{pct}", **r})

    # /* Part C — 상위 K건 의심 (검토 인력 상한 가정) */
    order = score_series.sort_values().index
    print("\n" + "=" * 72)
    print("Part C — 의심 점수가 가장 나쁜(낮은) 순으로 K건만 의심으로 보냄")
    print("=" * 72)

    for k in TOP_K_ALERTS:
        if k > n_test:
            continue
        top_idx = order[:k]
        pred_anomaly = pd.Series(False, index=test_df.index)
        pred_anomaly.loc[top_idx] = True
        r = confusion_and_rates(y_test, pred_anomaly.values)
        label = f"C_topK_{k}"
        print_block(f"상위 K={k}", r)
        rows.append({"experiment": label, "setting": f"K={k}", **r})

    summary = pd.DataFrame(rows)
    out_path = PROJECT_ROOT / "outputs" / "creditcard" / "if_eval_summary.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_path, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 72)
    print("요약 표 (동일 내용이 CSV로 저장됨:", out_path.name, ")")
    print("=" * 72)
    print(summary.to_string(index=False))
    print(
        f"\n(끝) 테스트 행: {n_test:,}  |  테스트 내 사기: {n_fraud_test:,}  |  CSV: {out_path}"
    )


if __name__ == "__main__":
    main()
