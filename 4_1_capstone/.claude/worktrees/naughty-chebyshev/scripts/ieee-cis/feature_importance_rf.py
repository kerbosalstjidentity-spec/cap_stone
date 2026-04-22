"""
IEEE-CIS: RF 특성 중요도 내보내기 (컬럼 이름 해석 가능).

- creditcard는 V1–V28 등 익명이라 도메인 해석이 제한적; IEEE-CIS는 card/addr/D/이메일 등 이름이 있음.
- 전처리 후 `ColumnTransformer.get_feature_names_out()` 과 `feature_importances_` 를 맞춤.
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
from sklearn.model_selection import train_test_split

from fds import IeeeCisFDS, make_preprocessor

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
TEST_SIZE = 0.25
RF_N_ESTIMATORS = 200
TOP_N = 40


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS RF feature importances")
    p.add_argument("--no-identity", action="store_true", help="train_identity 병합 생략")
    p.add_argument("--max-rows", type=int, default=None, metavar="N", help="처음 N행만 로드")
    p.add_argument("--top", type=int, default=TOP_N, help=f"상위 N개 저장 (기본 {TOP_N})")
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
    names = pre.get_feature_names_out()
    clf = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X_train_m, y_train)

    imp = pd.DataFrame({"feature": names, "importance": clf.feature_importances_})
    imp = imp.sort_values("importance", ascending=False).reset_index(drop=True)
    top = imp.head(args.top)

    out_dir = PROJECT_ROOT / "outputs" / "ieee_cis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rf_feature_importance.csv"
    top.to_csv(out_path, index=False, encoding="utf-8-sig")

    print("=== IEEE-CIS Random Forest — 특성 중요도 (상위) ===\n")
    print(f"행: {len(df):,}  학습 표본: {len(X_train):,}  identity: {not args.no_identity}")
    print(f"\n상위 {min(args.top, len(top))}개 → {out_path}\n")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
