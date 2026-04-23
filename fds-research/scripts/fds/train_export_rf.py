"""
스키마 v1에 맞춰 RandomForest 학습 후 배치 스코어링용 번들 저장.

번들: joblib(dict) — pipeline, schema_raw, feature_names, clf_step_name
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from policy_merge import decide_from_score  # noqa: E402
from schema import FDSSchema  # noqa: E402

RANDOM_STATE = 42


def build_pipeline(imputer_strategy: str) -> Pipeline:
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    imp = SimpleImputer(strategy=imputer_strategy)
    return Pipeline([("imputer", imp), ("clf", clf)])


def main() -> None:
    p = argparse.ArgumentParser(description="FDS RF 학습·번들 저장 (스키마 v1)")
    p.add_argument("--schema", type=Path, required=True, help="schemas/fds/schema_v1_*.yaml")
    p.add_argument("--train-csv", type=Path, required=True)
    p.add_argument("--nrows", type=int, default=None, help="학습 행 상한 (대용량 CSV 스모크용)")
    p.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "fds" / "model_bundle.joblib",
        help="저장할 joblib 경로",
    )
    p.add_argument(
        "--holdout-fraction",
        type=float,
        default=None,
        help="0~1 미만이면 stratified 홀드아웃만 평가·학습은 나머지로만 수행",
    )
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=None,
        help="홀드아웃 시 검증 지표 JSON 경로 (미지정 시 --out stem + .metrics.json)",
    )
    p.add_argument(
        "--thresholds",
        type=Path,
        default=PROJECT_ROOT / "policies" / "fds" / "thresholds_v1.yaml",
        help="홀드아웃 정책 지표(review/block 비율·Recall·FPR) 계산용",
    )
    args = p.parse_args()

    schema = FDSSchema.from_yaml(args.schema)
    df = pd.read_csv(args.train_csv, nrows=args.nrows)
    df = schema.prepare_frame(df)
    y = schema.labels_if_any(df)
    if y is None:
        raise ValueError("학습 CSV에 라벨 컬럼(Class 등)이 필요합니다.")

    X = schema.feature_matrix(df)
    ho = args.holdout_fraction
    if ho is not None and not (0 < ho < 1):
        raise ValueError("--holdout-fraction 은 0 초과 1 미만")

    metrics: dict | None = None
    if ho is not None:
        X_tr, X_ho, y_tr, y_ho = train_test_split(
            X,
            y,
            test_size=ho,
            stratify=y,
            random_state=RANDOM_STATE,
        )
        # SMOTE 적용 (데이터 불균형 해결)
        smote = SMOTE(random_state=RANDOM_STATE)
        X_tr, y_tr = smote.fit_resample(X_tr, y_tr)
        pipe = build_pipeline(schema.imputer_strategy())
        pipe.fit(X_tr.values, y_tr.values)
        X_ho_t = pipe.named_steps["imputer"].transform(X_ho.values)
        proba = pipe.named_steps["clf"].predict_proba(X_ho_t)[:, 1]
        yv = y_ho.values.astype(int)
        auc = float(roc_auc_score(yv, proba))
        pr = float(average_precision_score(yv, proba))

        block_min, review_min = 0.95, 0.35
        if args.thresholds.exists():
            with args.thresholds.open(encoding="utf-8") as f:
                th = yaml.safe_load(f)
            block_min = float(th["block_min"])
            review_min = float(th["review_min"])

        actions = [decide_from_score(float(s), block_min, review_min) for s in proba]
        n = len(yv)
        fraud = yv == 1
        normal = ~fraud
        n_fraud = int(fraud.sum())
        n_normal = int(normal.sum())
        in_queue = np.array([a in ("REVIEW", "BLOCK") for a in actions], dtype=bool)
        tp_q = int((in_queue & fraud).sum())
        fp_q = int((in_queue & normal).sum())
        fn_q = int((~in_queue & fraud).sum())
        recall_queue = tp_q / n_fraud if n_fraud else 0.0
        fpr_queue = fp_q / n_normal if n_normal else 0.0

        metrics = {
            "split": "stratified_holdout",
            "holdout_fraction": ho,
            "random_state": RANDOM_STATE,
            "n_train": int(len(X_tr)),
            "n_holdout": int(len(X_ho)),
            "holdout_fraud_rate": float(yv.mean()),
            "roc_auc_holdout": auc,
            "pr_auc_holdout": pr,
            "thresholds_file": str(args.thresholds) if args.thresholds.exists() else None,
            "block_min": block_min,
            "review_min": review_min,
            "holdout_queue_size_review_or_block": int(in_queue.sum()),
            "holdout_recall_in_queue": recall_queue,
            "holdout_fpr_in_queue_among_normal": fpr_queue,
            "holdout_confusion_queue": {"tp": tp_q, "fp": fp_q, "fn_outside_queue": fn_q},
        }
        mpath = args.metrics_out or args.out.with_suffix(".metrics.json")
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        print(f"지표 저장: {mpath}")
    else:
        # SMOTE 적용 (데이터 불균형 해결)
        smote = SMOTE(random_state=RANDOM_STATE)
        X, y = smote.fit_resample(X, y)
        pipe = build_pipeline(schema.imputer_strategy())
        pipe.fit(X.values, y.values)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "pipeline": pipe,
        "schema_raw": schema.raw,
        "feature_names": schema.feature_columns(),
        "schema_path": str(args.schema.resolve()),
        "train_csv": str(args.train_csv.resolve()),
        "holdout_fraction": ho,
    }
    joblib.dump(bundle, args.out)
    print(f"저장: {args.out}")
    print(f"  스키마: {schema.name} (v{schema.version})")
    fit_n = len(X) if ho is None else len(X_tr)
    print(f"  학습 행: {fit_n:,}  특성 수: {X.shape[1]}")


if __name__ == "__main__":
    main()
