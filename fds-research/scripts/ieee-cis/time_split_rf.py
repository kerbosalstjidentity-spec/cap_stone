"""
IEEE-CIS 시간 순 검증 (TransactionDT).

- 랜덤 stratified split이 아니라, 시간 순으로 앞 구간 학습·뒤 구간 검증.
- creditcard(Time은 상대초만 있고 동일 실험이 덜 의미 있음) 대비 확장 축.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IEEE_CIS_DIR = Path(__file__).resolve().parent
if str(IEEE_CIS_DIR) not in sys.path:
    sys.path.insert(0, str(IEEE_CIS_DIR))

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

from fds import IeeeCisFDS, make_preprocessor, split_train_val_by_time

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
RF_N_ESTIMATORS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS RF with time-ordered validation")
    p.add_argument("--no-identity", action="store_true", help="train_identity 병합 생략")
    p.add_argument("--max-rows", type=int, default=None, metavar="N", help="처음 N행만 로드")
    p.add_argument(
        "--test-fraction",
        type=float,
        default=0.25,
        help="시간 순 뒤쪽 이 비율을 검증 (기본 0.25)",
    )
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

    clf = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X_train_m, y_train)

    proba = clf.predict_proba(X_val_m)[:, 1]
    pred = (proba >= 0.5).astype(int)

    t0 = float(train_df["TransactionDT"].min())
    t1 = float(train_df["TransactionDT"].max())
    v0 = float(val_df["TransactionDT"].min())
    v1 = float(val_df["TransactionDT"].max())

    print("=== IEEE-CIS Random Forest — 시간 순 검증 (TransactionDT) ===\n")
    print(f"행: {len(df):,}  identity 병합: {not args.no_identity}")
    print(f"학습: {len(train_df):,}  검증: {len(val_df):,}  검증 사기율: {y_val.mean():.4%}")
    print(f"학습 TransactionDT 구간: [{t0:.0f}, {t1:.0f}]")
    print(f"검증 TransactionDT 구간: [{v0:.0f}, {v1:.0f}]\n")
    print(f"ROC-AUC:      {roc_auc_score(y_val, proba):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_val, proba):.4f}")
    print("\n--- classification_report (threshold=0.5) ---")
    print(classification_report(y_val, pred, digits=4))

    out_dir = PROJECT_ROOT / "outputs" / "ieee_cis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "time_split_rf_metrics.csv"
    pd.DataFrame(
        [
            {
                "rows": len(df),
                "test_fraction": args.test_fraction,
                "use_identity": not args.no_identity,
                "train_dt_min": t0,
                "train_dt_max": t1,
                "val_dt_min": v0,
                "val_dt_max": v1,
                "roc_auc": roc_auc_score(y_val, proba),
                "pr_auc": average_precision_score(y_val, proba),
            }
        ]
    ).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n요약 저장: {out_path}")


if __name__ == "__main__":
    main()
