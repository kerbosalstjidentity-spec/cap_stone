"""
IEEE-CIS: IF contamination 스윕 + (선택) 수치 일부만 IF, LOF 샘플.

- 전체 행에 LOF는 비용이 큼 → `sample_rows` 만큼만 LOF 학습 후 전체에 score_samples 불가(LOF는 predict).
  대표값으로 **학습 표본에만 LOF 점수**를 붙이고, 나머지는 NaN→0 처리 (실험용).
- 실험용: `--max-rows` 권장.

산출물: outputs/ieee_cis/if_sweep/sweep_metrics.csv
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
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.model_selection import train_test_split

from fds import IeeeCisFDS, make_preprocessor

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "outputs" / "ieee_cis" / "if_sweep"

RANDOM_STATE = 42
TEST_SIZE = 0.25
LGBM_N_ESTIMATORS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IF contamination sweep / LOF (IEEE-CIS)")
    p.add_argument("--no-identity", action="store_true")
    p.add_argument("--max-rows", type=int, default=80000)
    p.add_argument(
        "--contaminations",
        default="0.005,0.01,0.02,0.05",
        help="IF contamination 스윕 (쉼표)",
    )
    p.add_argument(
        "--if-numeric-only",
        type=int,
        default=0,
        metavar="K",
        help="0이면 전처리 후 전체 특성. K>0면 전처리 행렬에서 앞 K개 수치 열만 IF",
    )
    p.add_argument(
        "--lof-sample",
        type=int,
        default=0,
        metavar="N",
        help="0이면 LOF 생략. N>0면 학습 집합에서 N행만 LOF fit 후 score로 특성 1열 추가",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(use_identity=not args.no_identity, nrows=args.max_rows)
    X, y = fds.xy(df)

    X_train, X_val, y_train, y_val = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_STATE,
    )

    pre = make_preprocessor(X_train)
    X_train_m = pre.fit_transform(X_train)
    X_val_m = pre.transform(X_val)

    contams = [float(x.strip()) for x in args.contaminations.split(",") if x.strip()]
    rows_out = []

    for contam in contams:
        if args.if_numeric_only and args.if_numeric_only > 0:
            k = min(args.if_numeric_only, X_train_m.shape[1])
            if_mat = X_train_m[:, :k]
            if_val = X_val_m[:, :k]
        else:
            if_mat = X_train_m
            if_val = X_val_m

        if_model = IsolationForest(
            n_estimators=100,
            contamination=contam,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        if_model.fit(if_mat)
        train_if = -if_model.score_samples(if_mat)
        val_if = -if_model.score_samples(if_val)

        X_tr = np.column_stack([X_train_m, train_if])
        X_va = np.column_stack([X_val_m, val_if])
        cols = [f"f{i}" for i in range(X_tr.shape[1])]
        clf = LGBMClassifier(
            n_estimators=LGBM_N_ESTIMATORS,
            random_state=RANDOM_STATE,
            class_weight="balanced",
            n_jobs=-1,
            verbose=-1,
        )
        clf.fit(pd.DataFrame(X_tr, columns=cols), y_train)
        proba = clf.predict_proba(pd.DataFrame(X_va, columns=cols))[:, 1]
        rows_out.append(
            {
                "model": "lgbm_if_feature",
                "contamination": contam,
                "if_numeric_only_k": args.if_numeric_only or X_train_m.shape[1],
                "roc_auc": roc_auc_score(y_val, proba),
                "pr_auc": average_precision_score(y_val, proba),
            }
        )

    if args.lof_sample > 0:
        n = min(args.lof_sample, len(X_train_m))
        rng = np.random.RandomState(RANDOM_STATE)
        idx = rng.choice(len(X_train_m), size=n, replace=False)
        lof = LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.05, n_jobs=-1)
        lof.fit(X_train_m[idx])
        train_lof = -lof.score_samples(X_train_m).reshape(-1, 1)
        val_lof = -lof.score_samples(X_val_m).reshape(-1, 1)
        X_tr = np.column_stack([X_train_m, train_lof])
        X_va = np.column_stack([X_val_m, val_lof])
        cols = [f"f{i}" for i in range(X_tr.shape[1])]
        clf = LGBMClassifier(
            n_estimators=LGBM_N_ESTIMATORS,
            random_state=RANDOM_STATE,
            class_weight="balanced",
            n_jobs=-1,
            verbose=-1,
        )
        clf.fit(pd.DataFrame(X_tr, columns=cols), y_train)
        proba = clf.predict_proba(pd.DataFrame(X_va, columns=cols))[:, 1]
        rows_out.append(
            {
                "model": "lgbm_lof_partial",
                "contamination": np.nan,
                "if_numeric_only_k": np.nan,
                "roc_auc": roc_auc_score(y_val, proba),
                "pr_auc": average_precision_score(y_val, proba),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "sweep_metrics.csv"
    pd.DataFrame(rows_out).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장: {out_path}")
    print(pd.DataFrame(rows_out).to_string(index=False))


if __name__ == "__main__":
    main()
