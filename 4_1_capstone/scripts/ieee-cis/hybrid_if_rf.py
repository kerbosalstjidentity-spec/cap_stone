"""
IEEE-CIS: 비지도(IF 이상 점수) + 지도(RF / LightGBM).

- creditcard/hybrid_if_rf.py 와 동일 아이디어; 원시 다특성·identity 병합에 적용.
- IF는 라벨 없이 학습, -score_samples 를 '의심' 특성 1열로 붙임.
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
from sklearn.model_selection import train_test_split

from fds import IeeeCisFDS, make_preprocessor

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
TEST_SIZE = 0.25
ISOLATION_N_ESTIMATORS = 100
IF_CONTAMINATION = 0.01
RF_N_ESTIMATORS = 200
LGBM_N_ESTIMATORS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS IF + RF/LGBM hybrid")
    p.add_argument("--no-identity", action="store_true", help="train_identity 병합 생략")
    p.add_argument("--max-rows", type=int, default=None, metavar="N", help="처음 N행만 로드")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    X, y = fds.xy(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_STATE,
    )

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_test_m = pre.transform(X_test)

    if_model = IsolationForest(
        n_estimators=ISOLATION_N_ESTIMATORS,
        contamination=IF_CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if_model.fit(X_train_m)
    train_if = -if_model.score_samples(X_train_m)
    test_if = -if_model.score_samples(X_test_m)

    X_train_h = np.column_stack([X_train_m, train_if])
    X_test_h = np.column_stack([X_test_m, test_if])

    n_feat = X_train_m.shape[1]
    col_base = [f"f{i}" for i in range(n_feat)]
    col_hybrid = col_base + ["if_suspicion"]
    X_train_lgb = pd.DataFrame(X_train_m, columns=col_base)
    X_test_lgb = pd.DataFrame(X_test_m, columns=col_base)
    X_train_lgb_h = pd.DataFrame(X_train_h, columns=col_hybrid)
    X_test_lgb_h = pd.DataFrame(X_test_h, columns=col_hybrid)

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

    proba_rf_base = rf_base.predict_proba(X_test_m)[:, 1]
    proba_rf_hybrid = rf_hybrid.predict_proba(X_test_h)[:, 1]
    proba_lgbm_base = lgbm_base.predict_proba(X_test_lgb)[:, 1]
    proba_lgbm_hybrid = lgbm_hybrid.predict_proba(X_test_lgb_h)[:, 1]

    print("=== IEEE-CIS IF + RF / LightGBM (stratified 홀드아웃) ===\n")
    print(
        f"행: {len(df):,}  특성(원본): {X.shape[1]}  identity: {not args.no_identity}\n"
        f"IF: contamination={IF_CONTAMINATION}, n_estimators={ISOLATION_N_ESTIMATORS}\n"
    )

    def block(name: str, proba: np.ndarray) -> None:
        print(f"--- {name} ---")
        print(f"ROC-AUC:      {roc_auc_score(y_test, proba):.4f}")
        print(f"PR-AUC:       {average_precision_score(y_test, proba):.4f}")
        print(classification_report(y_test, (proba >= 0.5).astype(int), digits=4))
        print()

    block("RF baseline", proba_rf_base)
    block("RF + IF 특성", proba_rf_hybrid)
    block(f"LightGBM baseline (n={LGBM_N_ESTIMATORS})", proba_lgbm_base)
    block("LightGBM + IF 특성", proba_lgbm_hybrid)

    out_dir = PROJECT_ROOT / "outputs" / "ieee_cis"
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
