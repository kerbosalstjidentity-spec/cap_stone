"""
IEEE-CIS 지도 학습 베이스라인 (Random Forest + fds 전처리).

- Stratified 홀드아웃, ROC-AUC·PR-AUC·classification_report 출력.
- 선택적으로 상위 N행만 로드해 개발용으로 사용 (--max-rows).
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
from sklearn.model_selection import train_test_split

from fds import IeeeCisFDS, make_preprocessor

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RANDOM_STATE = 42
TEST_SIZE = 0.25
RF_N_ESTIMATORS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IEEE-CIS RF baseline (fds pipeline)")
    p.add_argument(
        "--no-identity",
        action="store_true",
        help="train_identity 병합 생략 (transaction만)",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        metavar="N",
        help="처음 N행만 로드 (개발·스모크 테스트용)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fds = IeeeCisFDS()
    df = fds.load_train(
        use_identity=not args.no_identity,
        nrows=args.max_rows,
    )
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

    clf = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X_train_m, y_train)

    proba = clf.predict_proba(X_test_m)[:, 1]
    pred = (proba >= 0.5).astype(int)

    print("=== IEEE-CIS Random Forest baseline (fds) ===\n")
    print(
        f"행: {len(df):,}  특성(원본 컬럼 수): {X.shape[1]}  "
        f"identity 병합: {not args.no_identity}"
    )
    print(f"학습: {len(X_train):,}  검증: {len(X_test):,}  검증 사기율: {y_test.mean():.4%}\n")
    print(f"ROC-AUC:      {roc_auc_score(y_test, proba):.4f}")
    print(f"PR-AUC:       {average_precision_score(y_test, proba):.4f}")
    print("\n--- classification_report (threshold=0.5) ---")
    print(classification_report(y_test, pred, digits=4))

    out_dir = PROJECT_ROOT / "outputs" / "ieee_cis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "baseline_rf_metrics.csv"
    pd.DataFrame(
        [
            {
                "rows": len(df),
                "features_raw": X.shape[1],
                "use_identity": not args.no_identity,
                "roc_auc": roc_auc_score(y_test, proba),
                "pr_auc": average_precision_score(y_test, proba),
            }
        ]
    ).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n요약 저장: {out_path}")


if __name__ == "__main__":
    main()
