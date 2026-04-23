"""
비지도(Isolation Forest 이상 점수) + 지도(Random Forest / LightGBM) 결합.

- IF는 train 특성만으로 fit (Class 미사용). score_samples로 각 행의 이상 점수를 구함.
- 점수는 -score_samples 로 변환해 '클수록 의심' 방향으로 맞춤 후, 원래 특성 옆에 1열로 붙임.
- RF·LightGBM은 (원특성 또는 원특성+IF점수)로 사기 분류를 학습한다.
- 동일 분할에서 baseline / hybrid의 ROC-AUC·PR-AUC를 비교 출력한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
TEST_SIZE = 0.25
ISOLATION_N_ESTIMATORS = 100
IF_CONTAMINATION = 0.01
RF_N_ESTIMATORS = 200
LGBM_N_ESTIMATORS = 200


def add_scaled_amount_time(
    df: pd.DataFrame, scaler_amount: RobustScaler, scaler_time: RobustScaler
) -> pd.DataFrame:
    out = df.copy()
    out["scaled_amount"] = scaler_amount.transform(out["Amount"].values.reshape(-1, 1))
    out["scaled_time"] = scaler_time.transform(out["Time"].values.reshape(-1, 1))
    return out


def build_x(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(["Time", "Amount", "Class"], axis=1)


def main() -> None:
    csv_path = PROJECT_ROOT / "data" / "creditcard.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"없음: {csv_path}")

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
    y_train = train_df["Class"].astype(int).values
    y_test = test_df["Class"].astype(int).values

    if_model = IsolationForest(
        n_estimators=ISOLATION_N_ESTIMATORS,
        contamination=IF_CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if_model.fit(X_train)
    # 낮은 score_samples = 더 이상 → 부호 반대로 '의심 강도'로 사용
    train_if = -if_model.score_samples(X_train)
    test_if = -if_model.score_samples(X_test)

    X_train_h = pd.concat(
        [X_train.reset_index(drop=True), pd.Series(train_if, name="if_suspicion")],
        axis=1,
    )
    X_test_h = pd.concat(
        [X_test.reset_index(drop=True), pd.Series(test_if, name="if_suspicion")],
        axis=1,
    )

    rf_base = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    rf_hybrid = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    lgbm_base = LGBMClassifier(
        n_estimators=LGBM_N_ESTIMATORS,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
        verbose=-1,
    )
    lgbm_hybrid = LGBMClassifier(
        n_estimators=LGBM_N_ESTIMATORS,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
        verbose=-1,
    )

    rf_base.fit(X_train, y_train)
    rf_hybrid.fit(X_train_h, y_train)
    lgbm_base.fit(X_train, y_train)
    lgbm_hybrid.fit(X_train_h, y_train)

    proba_rf_base = rf_base.predict_proba(X_test)[:, 1]
    proba_rf_hybrid = rf_hybrid.predict_proba(X_test_h)[:, 1]
    proba_lgbm_base = lgbm_base.predict_proba(X_test)[:, 1]
    proba_lgbm_hybrid = lgbm_hybrid.predict_proba(X_test_h)[:, 1]

    print("=== 비지도(IF 점수) + 지도(RF / LightGBM) — creditcard 홀드아웃 ===\n")
    print(
        f"학습 행: {len(X_train):,}  테스트 행: {len(X_test):,}  "
        f"테스트 사기 비율: {y_test.mean():.4%}"
    )
    print(f"IF: contamination={IF_CONTAMINATION}, n_estimators={ISOLATION_N_ESTIMATORS}\n")

    print("--- RF만 (원특성, IF 점수 없음) ---")
    print(f"ROC-AUC:      {roc_auc_score(y_test, proba_rf_base):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_test, proba_rf_base):.4f}")
    print(classification_report(y_test, (proba_rf_base >= 0.5).astype(int), digits=4))

    print("--- RF + IF 의심 점수 특성 (hybrid) ---")
    print(f"ROC-AUC:      {roc_auc_score(y_test, proba_rf_hybrid):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_test, proba_rf_hybrid):.4f}")
    print(classification_report(y_test, (proba_rf_hybrid >= 0.5).astype(int), digits=4))

    print(f"--- LightGBM만 (원특성, n_estimators={LGBM_N_ESTIMATORS}) ---")
    print(f"ROC-AUC:      {roc_auc_score(y_test, proba_lgbm_base):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_test, proba_lgbm_base):.4f}")
    print(classification_report(y_test, (proba_lgbm_base >= 0.5).astype(int), digits=4))

    print("--- LightGBM + IF 의심 점수 특성 (hybrid) ---")
    print(f"ROC-AUC:      {roc_auc_score(y_test, proba_lgbm_hybrid):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_test, proba_lgbm_hybrid):.4f}")
    print(classification_report(y_test, (proba_lgbm_hybrid >= 0.5).astype(int), digits=4))

    out_dir = PROJECT_ROOT / "outputs" / "creditcard"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmp_path = out_dir / "hybrid_if_rf_compare.csv"
    pd.DataFrame(
        {
            "model": [
                "rf_baseline",
                "rf_hybrid_if_feature",
                "lgbm_baseline",
                "lgbm_hybrid_if_feature",
            ],
            "roc_auc": [
                roc_auc_score(y_test, proba_rf_base),
                roc_auc_score(y_test, proba_rf_hybrid),
                roc_auc_score(y_test, proba_lgbm_base),
                roc_auc_score(y_test, proba_lgbm_hybrid),
            ],
            "pr_auc": [
                average_precision_score(y_test, proba_rf_base),
                average_precision_score(y_test, proba_rf_hybrid),
                average_precision_score(y_test, proba_lgbm_base),
                average_precision_score(y_test, proba_lgbm_hybrid),
            ],
        }
    ).to_csv(cmp_path, index=False, encoding="utf-8-sig")
    print(f"요약 저장: {cmp_path}")


if __name__ == "__main__":
    main()
