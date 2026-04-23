"""
시간 검증 + LGBM·RF 확률 블렌딩 최소 실험.

- 검증: `split_train_val_by_time` (학습=과거, 검증=뒤 구간).
- 동일 전처리 행렬에서 RF·LGBM 각각 확률 p_rf, p_lgbm 산출.
- p_blend(w) = w * p_lgbm + (1 - w) * p_rf, w ∈ [0, 1] 그리드.

산출:
- outputs/ieee_cis/time_split_blend_lgbm_rf_grid.csv
- outputs/ieee_cis/time_split_blend_lgbm_rf_summary.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IEEE_CIS_DIR = Path(__file__).resolve().parent
if str(IEEE_CIS_DIR) not in sys.path:
    sys.path.insert(0, str(IEEE_CIS_DIR))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from fds import (
    IeeeCisFDS,
    add_extended_prior_features,
    make_preprocessor,
    split_train_val_by_time,
)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "outputs" / "ieee_cis"

RANDOM_STATE = 42
RF_N_ESTIMATORS = 200
LGBM_N_ESTIMATORS = 300


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Time-split LGBM+RF probability blend")
    p.add_argument("--no-identity", action="store_true")
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--test-fraction", type=float, default=0.25)
    p.add_argument("--extended-priors", action="store_true")
    p.add_argument(
        "--grid",
        type=int,
        default=21,
        help="w를 0..1에서 몇 점으로 볼지 (기본 21)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    if args.extended_priors:
        df = add_extended_prior_features(df)

    train_df, val_df = split_train_val_by_time(df, test_size=args.test_fraction)
    X_train, y_train = fds.xy(train_df)
    X_val, y_val = fds.xy(val_df)

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_val_m = pre.transform(X_val)
    n_feat = X_train_m.shape[1]
    col_names = [f"f{i}" for i in range(n_feat)]
    X_train_df = pd.DataFrame(X_train_m, columns=col_names)
    X_val_df = pd.DataFrame(X_val_m, columns=col_names)

    rf = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    lgbm = LGBMClassifier(
        n_estimators=LGBM_N_ESTIMATORS,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
        verbose=-1,
    )

    rf.fit(X_train_m, y_train)
    lgbm.fit(X_train_df, y_train)

    p_rf = rf.predict_proba(X_val_m)[:, 1]
    p_lgbm = lgbm.predict_proba(X_val_df)[:, 1]
    yv = y_val.to_numpy()

    roc_rf = roc_auc_score(yv, p_rf)
    roc_lgbm = roc_auc_score(yv, p_lgbm)
    pr_rf = average_precision_score(yv, p_rf)
    pr_lgbm = average_precision_score(yv, p_lgbm)

    weights = np.linspace(0.0, 1.0, max(2, args.grid))
    rows = []
    for w in weights:
        p = w * p_lgbm + (1.0 - w) * p_rf
        rows.append(
            {
                "w_lgbm": float(w),
                "w_rf": float(1.0 - w),
                "roc_auc": roc_auc_score(yv, p),
                "pr_auc": average_precision_score(yv, p),
            }
        )

    grid = pd.DataFrame(rows)
    best_pr = grid.loc[grid["pr_auc"].idxmax()]
    best_roc = grid.loc[grid["roc_auc"].idxmax()]

    summary = pd.DataFrame(
        [
            {
                "rows": len(df),
                "train_rows": len(train_df),
                "val_rows": len(val_df),
                "use_identity": not args.no_identity,
                "extended_priors": args.extended_priors,
                "test_fraction": args.test_fraction,
                "roc_auc_rf_only": roc_rf,
                "pr_auc_rf_only": pr_rf,
                "roc_auc_lgbm_only": roc_lgbm,
                "pr_auc_lgbm_only": pr_lgbm,
                "best_pr_auc_w_lgbm": best_pr["w_lgbm"],
                "best_pr_auc": best_pr["pr_auc"],
                "best_roc_auc_w_lgbm": best_roc["w_lgbm"],
                "best_roc_auc": best_roc["roc_auc"],
            }
        ]
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid_path = OUT_DIR / "time_split_blend_lgbm_rf_grid.csv"
    summary_path = OUT_DIR / "time_split_blend_lgbm_rf_summary.csv"
    grid.to_csv(grid_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    print("=== 시간 검증 + LGBM·RF 확률 블렌딩 ===\n")
    print(f"행: {len(df):,}  검증: {len(val_df):,}  identity: {not args.no_identity}  priors: {args.extended_priors}\n")
    print(f"RF만:  ROC={roc_rf:.4f}  PR={pr_rf:.4f}")
    print(f"LGBM만: ROC={roc_lgbm:.4f}  PR={pr_lgbm:.4f}\n")
    print(f"PR-AUC 최대: w_lgbm={best_pr['w_lgbm']:.3f} PR={best_pr['pr_auc']:.4f}")
    print(f"ROC-AUC 최대: w_lgbm={best_roc['w_lgbm']:.3f} ROC={best_roc['roc_auc']:.4f}\n")
    print(f"그리드 저장: {grid_path}")
    print(f"요약 저장: {summary_path}")


if __name__ == "__main__":
    main()
