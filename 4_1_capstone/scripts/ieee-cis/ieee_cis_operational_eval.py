"""
IEEE-CIS 운영 평가 묶음: 시간 순 검증 + (선택) 집계·빈도·타깃 인코딩 + LGBM
+ 임계값 스윕(Fβ·비용·재현율 하한), PR 곡선, 캘리브레이션 곡선, (선택) isotonic 보정.

산출물: outputs/ieee_cis/operational/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

IEEE_CIS_DIR = Path(__file__).resolve().parent
if str(IEEE_CIS_DIR) not in sys.path:
    sys.path.insert(0, str(IEEE_CIS_DIR))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, roc_auc_score

from eval_metrics import (
    export_calibration_curve,
    export_pr_curve,
    threshold_scan,
)
from fds import (
    IeeeCisFDS,
    add_extended_prior_features,
    apply_frequency_encoding,
    apply_target_encoding_cv,
    make_preprocessor,
    split_train_val_by_time,
)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "outputs" / "ieee_cis" / "operational"

RANDOM_STATE = 42
LGBM_N_ESTIMATORS = 300


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS operational eval (thresholds, PR, calibration)")
    p.add_argument("--no-identity", action="store_true")
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--test-fraction", type=float, default=0.25)
    p.add_argument("--extended-priors", action="store_true", help="card/addr/email/device prior_n, prior_amt")
    p.add_argument(
        "--freq-encode-cols",
        default="",
        help="쉼표 구분: ProductCD,P_emaildomain,R_emaildomain (학습 빈도 인코딩)",
    )
    p.add_argument(
        "--target-encode-cols",
        default="",
        help="쉼표 구분: ProductCD (CV 타깃 인코딩, sklearn TargetEncoder)",
    )
    p.add_argument("--scale-pos-weight", action="store_true", help="LGBM scale_pos_weight = neg/pos")
    p.add_argument(
        "--calibrate",
        choices=["", "isotonic", "sigmoid"],
        default="",
        help="CalibratedClassifierCV on training (cv=3, no leakage on val)",
    )
    p.add_argument("--min-recall", type=float, default=0.25, help="임계값 요약: 재현율 하한")
    p.add_argument("--fp-cost", type=float, default=1.0)
    p.add_argument("--fn-cost", type=float, default=1.0)
    return p.parse_args()


def _parse_cols(s: str) -> list[str]:
    return [c.strip() for c in s.split(",") if c.strip()]


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    if args.extended_priors:
        df = add_extended_prior_features(df)

    train_df, val_df = split_train_val_by_time(df, test_size=args.test_fraction)
    X_train, y_train = fds.xy(train_df)
    X_val, y_val = fds.xy(val_df)

    fcols = _parse_cols(args.freq_encode_cols)
    tcols = _parse_cols(args.target_encode_cols)
    if fcols:
        X_train, X_val = apply_frequency_encoding(X_train, X_val, fcols)
    if tcols:
        X_train, X_val = apply_target_encoding_cv(X_train, y_train, X_val, tcols)

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_val_m = pre.transform(X_val)

    col_names = [f"f{i}" for i in range(X_train_m.shape[1])]
    X_train_df = pd.DataFrame(X_train_m, columns=col_names)
    X_val_df = pd.DataFrame(X_val_m, columns=col_names)

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

    if args.calibrate:
        clf = CalibratedClassifierCV(
            clf,
            method=args.calibrate,
            cv=3,
            n_jobs=-1,
        )

    clf.fit(X_train_df, y_train)
    proba = clf.predict_proba(X_val_df)[:, 1]

    roc = roc_auc_score(y_val, proba)
    pr = average_precision_score(y_val, proba)
    detail, summary = threshold_scan(
        y_val.values,
        proba,
        betas=(0.5, 1.0, 2.0),
        min_recall=args.min_recall,
        fp_cost=args.fp_cost,
        fn_cost=args.fn_cost,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    detail.to_csv(OUT_DIR / "threshold_scan_detail.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUT_DIR / "threshold_scan_summary.csv", index=False, encoding="utf-8-sig")
    export_pr_curve(y_val.values, proba, OUT_DIR / "pr_curve.csv")
    export_calibration_curve(y_val.values, proba, OUT_DIR / "calibration_curve.csv")

    meta = {
        "rows": int(len(df)),
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "use_identity": not args.no_identity,
        "extended_priors": args.extended_priors,
        "freq_encode_cols": fcols,
        "target_encode_cols": tcols,
        "scale_pos_weight": bool(args.scale_pos_weight),
        "spw_value": spw if args.scale_pos_weight else None,
        "calibrate": args.calibrate or None,
        "roc_auc": roc,
        "pr_auc": pr,
        "test_fraction": args.test_fraction,
    }
    (OUT_DIR / "run_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== IEEE-CIS operational eval (LGBM + validation) ===\n")
    print(f"ROC-AUC: {roc:.4f}  PR-AUC: {pr:.4f}")
    print(f"산출: {OUT_DIR}\n")
    print("--- threshold_scan_summary (일부) ---")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
