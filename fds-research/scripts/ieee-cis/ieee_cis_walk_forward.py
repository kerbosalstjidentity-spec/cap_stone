"""
IEEE-CIS walk-forward 시간 폴드: `walk_forward_time_splits` 로 학습·검증 분리 후 LGBM 평가.

산출물: outputs/ieee_cis/walk_forward/fold_metrics.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IEEE_CIS_DIR = Path(__file__).resolve().parent
if str(IEEE_CIS_DIR) not in sys.path:
    sys.path.insert(0, str(IEEE_CIS_DIR))

import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from fds import IeeeCisFDS, add_extended_prior_features, make_preprocessor, walk_forward_time_splits

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "outputs" / "ieee_cis" / "walk_forward"

RANDOM_STATE = 42
LGBM_N_ESTIMATORS = 300


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS walk-forward time folds")
    p.add_argument("--no-identity", action="store_true")
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--n-folds", type=int, default=4, help="시간 분위 구간 개수")
    p.add_argument("--extended-priors", action="store_true")
    p.add_argument("--scale-pos-weight", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    if args.extended_priors:
        df = add_extended_prior_features(df)

    folds = walk_forward_time_splits(df, n_folds=args.n_folds)
    if not folds:
        raise RuntimeError("유효한 fold가 없습니다. n_folds 또는 데이터를 확인하세요.")

    rows_out = []
    for fold_id, (train_df, val_df) in enumerate(folds, start=1):
        X_train, y_train = fds.xy(train_df)
        X_val, y_val = fds.xy(val_df)
        pre = make_preprocessor(X_train)
        X_train_m = pre.fit_transform(X_train)
        X_val_m = pre.transform(X_val)

        neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
        spw = float(neg) / float(pos) if pos else 1.0

        clf = LGBMClassifier(
            n_estimators=LGBM_N_ESTIMATORS,
            random_state=RANDOM_STATE,
            class_weight="balanced",
            n_jobs=-1,
            verbose=-1,
        )
        if args.scale_pos_weight:
            clf.set_params(class_weight=None, scale_pos_weight=spw)

        col_names = [f"f{i}" for i in range(X_train_m.shape[1])]
        clf.fit(pd.DataFrame(X_train_m, columns=col_names), y_train)
        proba = clf.predict_proba(pd.DataFrame(X_val_m, columns=col_names))[:, 1]

        roc = roc_auc_score(y_val, proba)
        pr = average_precision_score(y_val, proba)
        rows_out.append(
            {
                "fold": fold_id,
                "train_rows": len(train_df),
                "val_rows": len(val_df),
                "val_fraud_rate": float(y_val.mean()),
                "roc_auc": roc,
                "pr_auc": pr,
            }
        )
        print(
            f"fold {fold_id}: train={len(train_df):,} val={len(val_df):,} "
            f"ROC={roc:.4f} PR={pr:.4f} val_fraud%={y_val.mean():.4%}"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "fold_metrics.csv"
    pd.DataFrame(rows_out).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
