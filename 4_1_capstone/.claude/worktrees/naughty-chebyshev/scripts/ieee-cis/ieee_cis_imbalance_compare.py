"""
IEEE-CIS: 불균형 대응 소규모 비교 (동일 시간 검증 분할).

- LGBM `class_weight=balanced`
- LGBM `scale_pos_weight = neg/pos` (class_weight 해제)

산출물: outputs/ieee_cis/imbalance_compare/metrics.csv
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

from fds import IeeeCisFDS, make_preprocessor, split_train_val_by_time

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "outputs" / "ieee_cis" / "imbalance_compare"

RANDOM_STATE = 42
LGBM_N_ESTIMATORS = 250


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LGBM imbalance strategy compare")
    p.add_argument("--no-identity", action="store_true")
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--test-fraction", type=float, default=0.25)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    train_df, val_df = split_train_val_by_time(df, test_size=args.test_fraction)
    X_train, y_train = fds.xy(train_df)
    X_val, y_val = fds.xy(val_df)

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_val_m = pre.transform(X_val)
    cols = [f"f{i}" for i in range(X_train_m.shape[1])]
    X_train_df = pd.DataFrame(X_train_m, columns=cols)
    X_val_df = pd.DataFrame(X_val_m, columns=cols)

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    spw = float(neg) / float(pos) if pos else 1.0

    rows = []
    for name, clf in [
        (
            "lgbm_class_weight_balanced",
            LGBMClassifier(
                n_estimators=LGBM_N_ESTIMATORS,
                random_state=RANDOM_STATE,
                class_weight="balanced",
                n_jobs=-1,
                verbose=-1,
            ),
        ),
        (
            "lgbm_scale_pos_weight",
            LGBMClassifier(
                n_estimators=LGBM_N_ESTIMATORS,
                random_state=RANDOM_STATE,
                class_weight=None,
                scale_pos_weight=spw,
                n_jobs=-1,
                verbose=-1,
            ),
        ),
    ]:
        clf.fit(X_train_df, y_train)
        proba = clf.predict_proba(X_val_df)[:, 1]
        rows.append(
            {
                "model": name,
                "roc_auc": roc_auc_score(y_val, proba),
                "pr_auc": average_precision_score(y_val, proba),
                "scale_pos_weight": spw if name.endswith("scale_pos_weight") else None,
            }
        )
        print(f"{name}: ROC={rows[-1]['roc_auc']:.4f} PR={rows[-1]['pr_auc']:.4f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "metrics.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
