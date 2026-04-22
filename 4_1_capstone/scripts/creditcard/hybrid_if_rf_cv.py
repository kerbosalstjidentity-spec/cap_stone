"""
Isolation Forest 점수 + 지도(RF / LightGBM) — Stratified K-fold CV.

- 각 폴드에서 IF는 해당 폴드 학습 구간만으로 fit (누수 없음).
- 홀드아웃 한 번보다 평균·표준편차로 안정적으로 비교한다.
- 권장 모델: 평균 PR-AUC 최대 (불균형 사기에 적합). 동률이면 평균 ROC-AUC.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import RobustScaler

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
N_SPLITS = 5
ISOLATION_N_ESTIMATORS = 100
IF_CONTAMINATION = 0.01
RF_N_ESTIMATORS = 200
LGBM_N_ESTIMATORS = 200

MODEL_KEYS = (
    "rf_baseline",
    "rf_hybrid_if_feature",
    "lgbm_baseline",
    "lgbm_hybrid_if_feature",
)


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
    y = df["Class"].astype(int).values

    skf = StratifiedKFold(
        n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE
    )

    roc = {k: [] for k in MODEL_KEYS}
    pr = {k: [] for k in MODEL_KEYS}

    for fold, (train_idx, val_idx) in enumerate(skf.split(df, y), start=1):
        train_df = df.iloc[train_idx].reset_index(drop=True)
        val_df = df.iloc[val_idx].reset_index(drop=True)
        y_train = train_df["Class"].astype(int).values
        y_val = val_df["Class"].astype(int).values

        scaler_amount = RobustScaler()
        scaler_time = RobustScaler()
        scaler_amount.fit(train_df["Amount"].values.reshape(-1, 1))
        scaler_time.fit(train_df["Time"].values.reshape(-1, 1))

        train_df = add_scaled_amount_time(train_df, scaler_amount, scaler_time)
        val_df = add_scaled_amount_time(val_df, scaler_amount, scaler_time)

        X_train = build_x(train_df)
        X_val = build_x(val_df)

        if_model = IsolationForest(
            n_estimators=ISOLATION_N_ESTIMATORS,
            contamination=IF_CONTAMINATION,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        if_model.fit(X_train)
        train_if = -if_model.score_samples(X_train)
        val_if = -if_model.score_samples(X_val)

        X_train_h = pd.concat(
            [
                X_train.reset_index(drop=True),
                pd.Series(train_if, name="if_suspicion"),
            ],
            axis=1,
        )
        X_val_h = pd.concat(
            [
                X_val.reset_index(drop=True),
                pd.Series(val_if, name="if_suspicion"),
            ],
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

        probas = {
            "rf_baseline": rf_base.predict_proba(X_val)[:, 1],
            "rf_hybrid_if_feature": rf_hybrid.predict_proba(X_val_h)[:, 1],
            "lgbm_baseline": lgbm_base.predict_proba(X_val)[:, 1],
            "lgbm_hybrid_if_feature": lgbm_hybrid.predict_proba(X_val_h)[:, 1],
        }

        for key in MODEL_KEYS:
            p = probas[key]
            roc[key].append(roc_auc_score(y_val, p))
            pr[key].append(average_precision_score(y_val, p))

        print(
            f"폴드 {fold}/{N_SPLITS} 완료 — "
            f"검증 사기 비율 {y_val.mean():.4%}"
        )

    rows = []
    for key in MODEL_KEYS:
        r = np.array(roc[key])
        p = np.array(pr[key])
        rows.append(
            {
                "model": key,
                "roc_auc_mean": float(r.mean()),
                "roc_auc_std": float(r.std(ddof=0)),
                "pr_auc_mean": float(p.mean()),
                "pr_auc_std": float(p.std(ddof=0)),
            }
        )

    out_dir = PROJECT_ROOT / "outputs" / "creditcard"
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_path = out_dir / "hybrid_if_rf_cv_compare.csv"
    summary = pd.DataFrame(rows).sort_values(
        ["pr_auc_mean", "roc_auc_mean"], ascending=[False, False]
    )
    summary.to_csv(cv_path, index=False, encoding="utf-8-sig")

    best = summary.iloc[0]

    rec_path = out_dir / "hybrid_if_recommendation.txt"
    text = (
        "평가 정책 (이 프로젝트 기본안)\n"
        "- 사기처럼 극단적 불균형에서는 순위 품질을 PR-AUC(평균)로 1순위로 둔다.\n"
        "- 동률이면 ROC-AUC(평균)로 가른다.\n"
        "- 단일 홀드아웃(hybrid_if_rf.py)은 빠른 참고용; 최종 비교는 이 CV 표를 우선한다.\n\n"
        f"Stratified {N_SPLITS}-fold, random_state={RANDOM_STATE}\n"
        f"권장 모델: {best['model']}\n"
        f"  pr_auc_mean={best['pr_auc_mean']:.6f} (std={best['pr_auc_std']:.6f})\n"
        f"  roc_auc_mean={best['roc_auc_mean']:.6f} (std={best['roc_auc_std']:.6f})\n"
    )
    rec_path.write_text(text, encoding="utf-8")

    print("\n=== Stratified CV 요약 (PR-AUC 평균 내림차순) ===\n")
    print(summary.to_string(index=False))
    print(f"\n저장: {cv_path}")
    print(f"권장 메모: {rec_path}")


if __name__ == "__main__":
    main()
