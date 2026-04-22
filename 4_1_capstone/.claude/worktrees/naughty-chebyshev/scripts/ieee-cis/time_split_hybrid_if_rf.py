"""
IEEE-CIS: 시간 순 검증 + IF 이상 점수 + RF / LightGBM (한 스크립트에서 비교).

- 검증: `split_train_val_by_time` (미래 구간에 가깝게).
- IF는 학습 구간 특성만으로 fit, 검증 구간에 score_samples.
- 선택: `fds.add_card1_prior_features` — 동일 card1 이전 건수·누적 금액 (집계 특성).
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
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

from fds import (
    IeeeCisFDS,
    add_card1_prior_features,
    make_preprocessor,
    split_train_val_by_time,
)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
ISOLATION_N_ESTIMATORS = 100
IF_CONTAMINATION = 0.01
RF_N_ESTIMATORS = 200
LGBM_N_ESTIMATORS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS time-split + IF hybrid + RF/LGBM")
    p.add_argument("--no-identity", action="store_true", help="train_identity 병합 생략")
    p.add_argument("--max-rows", type=int, default=None, metavar="N", help="처음 N행만 로드")
    p.add_argument(
        "--test-fraction",
        type=float,
        default=0.25,
        help="시간 순 뒤쪽 검증 비율 (기본 0.25)",
    )
    p.add_argument(
        "--card-prior-features",
        action="store_true",
        help="card1 기준 이전 건수·누적 금액 특성 추가 (TransactionDT 순)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    if args.card_prior_features:
        df = add_card1_prior_features(df)

    train_df, val_df = split_train_val_by_time(df, test_size=args.test_fraction)
    X_train, y_train = fds.xy(train_df)
    X_val, y_val = fds.xy(val_df)

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_val_m = pre.transform(X_val)

    if_model = IsolationForest(
        n_estimators=ISOLATION_N_ESTIMATORS,
        contamination=IF_CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if_model.fit(X_train_m)
    train_if = -if_model.score_samples(X_train_m)
    val_if = -if_model.score_samples(X_val_m)

    X_train_h = np.column_stack([X_train_m, train_if])
    X_val_h = np.column_stack([X_val_m, val_if])

    n_feat = X_train_m.shape[1]
    col_base = [f"f{i}" for i in range(n_feat)]
    col_hybrid = col_base + ["if_suspicion"]
    X_train_lgb = pd.DataFrame(X_train_m, columns=col_base)
    X_val_lgb = pd.DataFrame(X_val_m, columns=col_base)
    X_train_lgb_h = pd.DataFrame(X_train_h, columns=col_hybrid)
    X_val_lgb_h = pd.DataFrame(X_val_h, columns=col_hybrid)

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

    rf_base.fit(X_train_m, y_train)
    rf_hybrid.fit(X_train_h, y_train)
    lgbm_base.fit(X_train_lgb, y_train)
    lgbm_hybrid.fit(X_train_lgb_h, y_train)

    proba_rf_base = rf_base.predict_proba(X_val_m)[:, 1]
    proba_rf_hybrid = rf_hybrid.predict_proba(X_val_h)[:, 1]
    proba_lgbm_base = lgbm_base.predict_proba(X_val_lgb)[:, 1]
    proba_lgbm_hybrid = lgbm_hybrid.predict_proba(X_val_lgb_h)[:, 1]

    tmax_tr = float(train_df["TransactionDT"].max())
    tmin_val = float(val_df["TransactionDT"].min())

    print("=== IEEE-CIS 시간 순 검증 + IF + RF / LightGBM ===\n")
    print(
        f"행: {len(df):,}  특성(원본): {X_train.shape[1]}  identity: {not args.no_identity}  "
        f"card1_prior: {args.card_prior_features}"
    )
    print(
        f"학습: {len(train_df):,}  검증: {len(val_df):,}  "
        f"검증 사기율: {y_val.mean():.4%}  test_fraction={args.test_fraction}"
    )
    print(f"학습 TransactionDT max → 검증 min: {tmax_tr:.0f} / {tmin_val:.0f}")
    print(f"IF: contamination={IF_CONTAMINATION}, n_estimators={ISOLATION_N_ESTIMATORS}\n")

    def block(name: str, proba: np.ndarray) -> None:
        print(f"--- {name} ---")
        print(f"ROC-AUC:      {roc_auc_score(y_val, proba):.4f}")
        print(f"PR-AUC:       {average_precision_score(y_val, proba):.4f}")
        print(classification_report(y_val, (proba >= 0.5).astype(int), digits=4))
        print()

    block("RF baseline", proba_rf_base)
    block("RF + IF 특성", proba_rf_hybrid)
    block(f"LightGBM baseline (n={LGBM_N_ESTIMATORS})", proba_lgbm_base)
    block("LightGBM + IF 특성", proba_lgbm_hybrid)

    out_dir = PROJECT_ROOT / "outputs" / "ieee_cis"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmp_path = out_dir / "time_split_hybrid_if_rf_compare.csv"
    meta = {
        "time_split": True,
        "test_fraction": args.test_fraction,
        "use_identity": not args.no_identity,
        "card1_prior_features": args.card_prior_features,
        "rows": len(df),
        "train_dt_max": tmax_tr,
        "val_dt_min": tmin_val,
    }
    rows_out = []
    for name, proba in [
        ("rf_baseline", proba_rf_base),
        ("rf_hybrid_if_feature", proba_rf_hybrid),
        ("lgbm_baseline", proba_lgbm_base),
        ("lgbm_hybrid_if_feature", proba_lgbm_hybrid),
    ]:
        row = {"model": name, "roc_auc": roc_auc_score(y_val, proba), "pr_auc": average_precision_score(y_val, proba)}
        row.update(meta)
        rows_out.append(row)
    pd.DataFrame(rows_out).to_csv(cmp_path, index=False, encoding="utf-8-sig")
    print(f"요약 저장: {cmp_path}")


if __name__ == "__main__":
    main()
