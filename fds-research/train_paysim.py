"""PaySim 학습 스크립트 — Isolation Forest + Random Forest 하이브리드 (W5.5-#3).

블로그 12 의 IF+RF 하이브리드 패턴을 PaySim 도메인으로 이식한다. 입력은
``scripts.paysim.load.load_paysim`` 로 표준화한 6.36M 행 PaySim CSV. 사기는
TRANSFER+CASH_OUT 에만 존재(0.13%)하므로 두 타입에 학습·평가 집중한다.

학습 파이프라인:
1) 표준 컬럼 + 파생 피처(잔액 모순, 비율) 추출
2) Stratified holdout split
3) IF fit on train → ``if_suspicion = -score_samples`` (양수=의심 큼)
4) RF fit on (raw features + if_suspicion), ``class_weight=balanced_subsample``
5) holdout AUC / PR-AUC / 큐(REVIEW+BLOCK) 리콜 기록
6) ``outputs/fds/model_bundle_paysim.joblib`` 저장

번들 스키마 (기존 ``model_bundle_open_full.joblib`` 답습):
    {
        "domain": "paysim",
        "if_model": IsolationForest,
        "rf_model": RandomForestClassifier,
        "feature_names": [...],
        "type_categories": ["TRANSFER", "CASH_OUT"],
        "trained_at": "2026-05-05T...",
        "metrics": {...},
    }

사용:
    python train_paysim.py --max-rows 200000 --out outputs/fds/model_bundle_paysim_smoke.joblib
    python train_paysim.py                 # full
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.paysim.load import load_paysim  # noqa: E402

RANDOM_STATE = 42
TYPE_CATEGORIES = ("TRANSFER", "CASH_OUT")

NUMERIC_FEATURES: tuple[str, ...] = (
    "step",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "errorBalanceOrig",
    "errorBalanceDest",
    "amount_to_oldbalance_ratio",
    "is_dest_merchant",
    "type_TRANSFER",
    "type_CASH_OUT",
)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """PaySim 원본 컬럼 → 학습용 수치 피처 데이터프레임.

    - 잔액 모순(error*): 정상 거래는 0 근방, 사기는 비대칭 큰 값
    - 비율: amount / (oldbalanceOrg + 1) — 잔액 대비 거래 비중
    - merchant 플래그: nameDest 가 'M' 으로 시작하면 가맹점 (사기 거의 없음)
    - one-hot: TRANSFER / CASH_OUT
    """
    out = pd.DataFrame(index=df.index)
    out["step"] = df["step"].astype("float32")
    out["amount"] = df["amount"].astype("float32")
    out["oldbalanceOrg"] = df["oldbalanceOrg"].astype("float32")
    out["newbalanceOrig"] = df["newbalanceOrig"].astype("float32")
    out["oldbalanceDest"] = df["oldbalanceDest"].astype("float32")
    out["newbalanceDest"] = df["newbalanceDest"].astype("float32")

    out["errorBalanceOrig"] = (
        df["oldbalanceOrg"] - df["amount"] - df["newbalanceOrig"]
    ).astype("float32")
    out["errorBalanceDest"] = (
        df["oldbalanceDest"] + df["amount"] - df["newbalanceDest"]
    ).astype("float32")
    out["amount_to_oldbalance_ratio"] = (
        df["amount"] / (df["oldbalanceOrg"].astype("float32") + 1.0)
    ).astype("float32")

    out["is_dest_merchant"] = df["nameDest"].str.startswith("M").astype("int8")

    type_str = df["type"].astype("string")
    out["type_TRANSFER"] = (type_str == "TRANSFER").astype("int8")
    out["type_CASH_OUT"] = (type_str == "CASH_OUT").astype("int8")

    return out[list(NUMERIC_FEATURES)]


def evaluate_holdout(
    if_model: IsolationForest,
    rf_model: RandomForestClassifier,
    X_holdout: pd.DataFrame,
    y_holdout: np.ndarray,
    block_min: float,
    review_min: float,
) -> dict:
    if_suspicion = -if_model.score_samples(X_holdout.values)
    X_h = X_holdout.copy()
    X_h["if_suspicion"] = if_suspicion.astype("float32")

    proba = rf_model.predict_proba(X_h.values)[:, 1]
    auc = float(roc_auc_score(y_holdout, proba))
    pr = float(average_precision_score(y_holdout, proba))

    in_queue = proba >= review_min
    block = proba >= block_min
    fraud = y_holdout == 1
    normal = ~fraud
    n_fraud = int(fraud.sum())
    n_normal = int(normal.sum())

    tp_q = int((in_queue & fraud).sum())
    fp_q = int((in_queue & normal).sum())
    fn_outside = int((~in_queue & fraud).sum())
    return {
        "n_holdout": int(len(y_holdout)),
        "n_fraud_holdout": n_fraud,
        "fraud_rate_holdout": float(fraud.mean()),
        "roc_auc": auc,
        "pr_auc": pr,
        "block_min": block_min,
        "review_min": review_min,
        "block_count": int(block.sum()),
        "queue_count": int(in_queue.sum()),
        "recall_in_queue": tp_q / n_fraud if n_fraud else 0.0,
        "fpr_in_queue": fp_q / n_normal if n_normal else 0.0,
        "confusion_queue": {"tp": tp_q, "fp": fp_q, "fn_outside_queue": fn_outside},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="PaySim IF+RF 하이브리드 학습")
    ap.add_argument("--csv", type=Path, default=None, help="PaySim CSV 경로 (기본: data/paysim.csv)")
    ap.add_argument("--max-rows", type=int, default=None, help="입력 상한(스모크용)")
    ap.add_argument("--holdout-fraction", type=float, default=0.2)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "outputs" / "fds" / "model_bundle_paysim.joblib",
    )
    ap.add_argument("--rf-estimators", type=int, default=200)
    ap.add_argument("--if-estimators", type=int, default=100)
    ap.add_argument("--if-contamination", type=float, default=0.001)
    ap.add_argument("--block-min", type=float, default=0.95)
    ap.add_argument("--review-min", type=float, default=0.35)
    ap.add_argument(
        "--class-weight",
        choices=["balanced", "balanced_subsample", "none"],
        default="balanced_subsample",
        help="RF class_weight 옵션 — none 은 SMOTE 단계(W5.5-#6)에서 사용",
    )
    args = ap.parse_args()

    print("[paysim-train] loading...")
    df = load_paysim(path=args.csv, types=TYPE_CATEGORIES, sample=args.max_rows)
    print(f"[paysim-train] loaded {len(df):,} rows, fraud={int(df['isFraud'].sum())}")

    X = build_features(df)
    y = df["isFraud"].astype("int8").values

    X_tr, X_ho, y_tr, y_ho = train_test_split(
        X,
        y,
        test_size=args.holdout_fraction,
        stratify=y,
        random_state=RANDOM_STATE,
    )
    print(f"[paysim-train] train={len(X_tr):,} holdout={len(X_ho):,}")

    print("[paysim-train] fitting IsolationForest...")
    if_model = IsolationForest(
        n_estimators=args.if_estimators,
        contamination=args.if_contamination,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if_model.fit(X_tr.values)
    if_suspicion_tr = -if_model.score_samples(X_tr.values)
    X_tr_h = X_tr.copy()
    X_tr_h["if_suspicion"] = if_suspicion_tr.astype("float32")

    print("[paysim-train] fitting RandomForest...")
    rf_model = RandomForestClassifier(
        n_estimators=args.rf_estimators,
        max_depth=None,
        class_weight=None if args.class_weight == "none" else args.class_weight,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    rf_model.fit(X_tr_h.values, y_tr)

    metrics = evaluate_holdout(
        if_model, rf_model, X_ho, y_ho, args.block_min, args.review_min
    )
    metrics["class_weight"] = args.class_weight
    metrics["if_contamination"] = args.if_contamination
    metrics["rf_estimators"] = args.rf_estimators
    print(json.dumps(metrics, indent=2, ensure_ascii=False))

    feature_names_with_if = list(NUMERIC_FEATURES) + ["if_suspicion"]
    bundle = {
        "domain": "paysim",
        "if_model": if_model,
        "rf_model": rf_model,
        "feature_names": feature_names_with_if,
        "raw_feature_names": list(NUMERIC_FEATURES),
        "type_categories": list(TYPE_CATEGORIES),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_train": int(len(X_tr)),
        "n_holdout": int(len(X_ho)),
        "metrics": metrics,
        "block_min": args.block_min,
        "review_min": args.review_min,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    metrics_path = args.out.with_suffix(".metrics.json")
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[paysim-train] saved bundle: {args.out}")
    print(f"[paysim-train] saved metrics: {metrics_path}")


if __name__ == "__main__":
    main()
