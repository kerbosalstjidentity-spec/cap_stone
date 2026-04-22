"""
data/open/ 대회용 지도 학습 (Random Forest).

- train.csv 는 Class 컬럼이 없어 라벨이 있는 val.csv 로 학습·홀드아웃 평가합니다.
- test.csv 에 대해 예측해 data/open/submission_supervised*.csv 로 저장합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPEN = PROJECT_ROOT / "data" / "open"

RANDOM_STATE = 42
TEST_SIZE = 0.2
FEATURE_COLS = [f"V{i}" for i in range(1, 31)]


def load_xy(path: Path) -> tuple[pd.DataFrame, pd.Series | None]:
    df = pd.read_csv(path)
    if "Class" not in df.columns:
        x = df[FEATURE_COLS]
        return x, None
    x = df[FEATURE_COLS]
    y = df["Class"].astype(int)
    return x, y


def main() -> None:
    val_path = OPEN / "val.csv"
    test_path = OPEN / "test.csv"

    if not val_path.exists():
        raise FileNotFoundError(f"없음: {val_path}")
    if not test_path.exists():
        raise FileNotFoundError(f"없음: {test_path}")

    X, y = load_xy(val_path)
    if y is None:
        raise ValueError("val.csv 에 Class 가 있어야 합니다.")

    X_train, X_val, y_train, y_val = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_STATE,
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_val)[:, 1]
    pred = (proba >= 0.5).astype(int)

    print("=== 지도 학습 (Random Forest) — data/open/val 홀드아웃 ===\n")
    print(f"학습 행: {len(X_train):,}  검증 행: {len(X_val):,}")
    print(f"검증 사기 비율: {y_val.mean():.4%}\n")
    print(f"ROC-AUC:        {roc_auc_score(y_val, proba):.4f}")
    print(f"PR-AUC (avg):   {average_precision_score(y_val, proba):.4f}")
    print("\n--- classification_report (threshold=0.5) ---")
    print(classification_report(y_val, pred, digits=4))

    X_test, _ = load_xy(test_path)
    test_ids = pd.read_csv(test_path, usecols=["ID"])["ID"]
    test_proba = clf.predict_proba(X_test)[:, 1]

    proba_path = OPEN / "submission_supervised_proba.csv"
    pd.DataFrame({"ID": test_ids, "Class": test_proba}).to_csv(proba_path, index=False)

    bin_path = OPEN / "submission_supervised.csv"
    pd.DataFrame({"ID": test_ids, "Class": (test_proba >= 0.5).astype(int)}).to_csv(bin_path, index=False)

    print(f"\n저장: {proba_path}  (Class = 사기 확률, AUC 제출용으로 흔함)")
    print(f"저장: {bin_path}       (Class = 0 또는 1, threshold=0.5)")


if __name__ == "__main__":
    main()
