"""
스키마 v1에 맞춰 RandomForest 학습 후 배치 스코어링용 번들 저장.

번들: joblib(dict) — pipeline, schema_raw, feature_names, clf_step_name

평가 방식:
  --holdout-fraction  : 단순 stratified 홀드아웃 (사기 건수가 충분할 때)
  --cv-folds N        : Stratified K-Fold CV (권장 — 라벨 데이터가 적을 때)
                        각 fold 내부에서만 SMOTE 적용, 테스트 fold는 원본 유지.
                        최종 모델은 전체 데이터로 재학습.
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
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE


def _impute_before_smote(
    X_raw: np.ndarray,
    strategy: str,
    *,
    fitted_imp: "SimpleImputer | None" = None,
) -> "tuple[np.ndarray, SimpleImputer]":
    """NaN이 있을 때 SMOTE 전에 imputer를 먼저 적용.

    fitted_imp가 있으면 transform만 수행 (테스트 fold 또는 OOF loop),
    없으면 fit_transform 후 fitted imputer를 반환.
    파이프라인 내부 imputer와 별개로 SMOTE 호환성을 위해서만 사용.
    """
    if not np.isnan(X_raw).any():
        imp = fitted_imp or SimpleImputer(strategy=strategy)
        if fitted_imp is None:
            imp.fit(X_raw)
        return X_raw, imp
    imp = fitted_imp or SimpleImputer(strategy=strategy)
    if fitted_imp is None:
        X_out = imp.fit_transform(X_raw)
    else:
        X_out = imp.transform(X_raw)
    return X_out, imp

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


def _load_thresholds(path: Path) -> tuple[float, float]:
    block_min, review_min = 0.5, 0.35
    if path.exists():
        with path.open(encoding="utf-8") as f:
            th = yaml.safe_load(f)
        block_min = float(th["block_min"])
        review_min = float(th["review_min"])
    return block_min, review_min


def _queue_metrics(
    yv: np.ndarray,
    proba: np.ndarray,
    block_min: float,
    review_min: float,
) -> dict:
    actions = [decide_from_score(float(s), block_min, review_min) for s in proba]
    fraud = yv == 1
    normal = ~fraud
    n_fraud = int(fraud.sum())
    n_normal = int(normal.sum())
    in_queue = np.array([a in ("REVIEW", "BLOCK") for a in actions], dtype=bool)
    tp_q = int((in_queue & fraud).sum())
    fp_q = int((in_queue & normal).sum())
    fn_q = int((~in_queue & fraud).sum())
    return {
        "queue_size": int(in_queue.sum()),
        "recall_in_queue": tp_q / n_fraud if n_fraud else 0.0,
        "fpr_in_queue": fp_q / n_normal if n_normal else 0.0,
        "confusion_queue": {"tp": tp_q, "fp": fp_q, "fn_outside_queue": fn_q},
    }


def run_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int,
    imputer_strategy: str,
    block_min: float,
    review_min: float,
) -> tuple[dict, Pipeline]:
    """
    Stratified K-Fold CV.
    - SMOTE는 각 fold의 훈련 분할에만 적용 (테스트 fold는 원본 유지).
    - 최종 모델은 전체 데이터로 재학습.
    반환: (metrics_dict, final_pipeline)
    """
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    X_arr = X.values
    y_arr = y.values.astype(int)

    fold_aucs: list[float] = []
    fold_prs: list[float] = []
    fold_n_fraud: list[int] = []

    for fold_i, (tr_idx, te_idx) in enumerate(skf.split(X_arr, y_arr), 1):
        X_tr_raw, X_te = X_arr[tr_idx], X_arr[te_idx]
        y_tr_raw, y_te = y_arr[tr_idx], y_arr[te_idx]

        # NaN 포함 데이터에서 SMOTE 호환을 위해 선처리 imputation
        X_tr_clean, fold_imp = _impute_before_smote(X_tr_raw, imputer_strategy)
        X_te_clean, _ = _impute_before_smote(X_te, imputer_strategy, fitted_imp=fold_imp)

        smote = SMOTE(random_state=RANDOM_STATE)
        X_tr, y_tr = smote.fit_resample(X_tr_clean, y_tr_raw)

        pipe = build_pipeline(imputer_strategy)
        pipe.fit(X_tr, y_tr)

        proba = pipe.named_steps["clf"].predict_proba(X_te_clean)[:, 1]

        n_pos = int(y_te.sum())
        fold_n_fraud.append(n_pos)

        if n_pos == 0:
            print(f"  [fold {fold_i}] 테스트 fold에 사기 0건 — ROC/PR 계산 불가, 건너뜀")
            continue

        fold_aucs.append(float(roc_auc_score(y_te, proba)))
        fold_prs.append(float(average_precision_score(y_te, proba)))
        print(
            f"  [fold {fold_i}/{n_splits}] "
            f"fraud={n_pos}  ROC-AUC={fold_aucs[-1]:.4f}  PR-AUC={fold_prs[-1]:.4f}"
        )

    # 최종 모델: 전체 데이터로 재학습 (SMOTE 포함)
    X_full_clean, full_imp = _impute_before_smote(X_arr, imputer_strategy)
    smote_full = SMOTE(random_state=RANDOM_STATE)
    X_full, y_full = smote_full.fit_resample(X_full_clean, y_arr)
    final_pipe = build_pipeline(imputer_strategy)
    final_pipe.fit(X_full, y_full)

    # 전체 예측(out-of-fold 집계) → 큐 지표
    oof_proba = np.zeros(len(y_arr))
    for tr_idx, te_idx in skf.split(X_arr, y_arr):
        X_tr_raw, X_te = X_arr[tr_idx], X_arr[te_idx]
        y_tr_raw = y_arr[tr_idx]
        X_tr_c, oof_imp = _impute_before_smote(X_tr_raw, imputer_strategy)
        X_te_c, _ = _impute_before_smote(X_te, imputer_strategy, fitted_imp=oof_imp)
        smote2 = SMOTE(random_state=RANDOM_STATE)
        X_tr2, y_tr2 = smote2.fit_resample(X_tr_c, y_tr_raw)
        p2 = build_pipeline(imputer_strategy)
        p2.fit(X_tr2, y_tr2)
        oof_proba[te_idx] = p2.named_steps["clf"].predict_proba(X_te_c)[:, 1]

    q = _queue_metrics(y_arr, oof_proba, block_min, review_min)

    metrics = {
        "eval_method": "stratified_kfold_cv",
        "n_splits": n_splits,
        "n_total": len(y_arr),
        "n_fraud_total": int(y_arr.sum()),
        "n_fraud_per_fold": fold_n_fraud,
        "random_state": RANDOM_STATE,
        "roc_auc_mean": float(np.mean(fold_aucs)) if fold_aucs else None,
        "roc_auc_std": float(np.std(fold_aucs)) if fold_aucs else None,
        "roc_auc_per_fold": fold_aucs,
        "pr_auc_mean": float(np.mean(fold_prs)) if fold_prs else None,
        "pr_auc_std": float(np.std(fold_prs)) if fold_prs else None,
        "pr_auc_per_fold": fold_prs,
        "note": (
            "SMOTE는 각 fold 훈련 분할에만 적용. "
            "최종 모델은 전체 데이터 재학습. "
            "큐 지표는 out-of-fold 예측 기준."
        ),
        "oof_queue_size": q["queue_size"],
        "oof_recall_in_queue": q["recall_in_queue"],
        "oof_fpr_in_queue": q["fpr_in_queue"],
        "oof_confusion_queue": q["confusion_queue"],
    }
    return metrics, final_pipe


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
        "--cv-folds",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Stratified K-Fold CV (권장). "
            "라벨 데이터 소규모일 때 --holdout-fraction 대신 사용. "
            "SMOTE는 각 fold 훈련 분할에만 적용."
        ),
    )
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=None,
        help="검증 지표 JSON 경로 (미지정 시 --out stem + .metrics.json)",
    )
    p.add_argument(
        "--thresholds",
        type=Path,
        default=PROJECT_ROOT / "policies" / "fds" / "thresholds_v1.yaml",
        help="정책 지표(review/block 비율·Recall·FPR) 계산용",
    )
    args = p.parse_args()

    if args.holdout_fraction is not None and args.cv_folds is not None:
        raise ValueError("--holdout-fraction 과 --cv-folds 는 동시에 사용 불가")

    schema = FDSSchema.from_yaml(args.schema)
    df = pd.read_csv(args.train_csv, nrows=args.nrows)
    df = schema.prepare_frame(df)
    y = schema.labels_if_any(df)
    if y is None:
        raise ValueError("학습 CSV에 라벨 컬럼(Class 등)이 필요합니다.")

    X = schema.feature_matrix(df)
    block_min, review_min = _load_thresholds(args.thresholds)
    mpath = args.metrics_out or args.out.with_suffix(".metrics.json")

    # ── CV 평가 ─────────────────────────────────────────────────────────────
    if args.cv_folds is not None:
        if args.cv_folds < 2:
            raise ValueError("--cv-folds 는 2 이상이어야 합니다.")
        n_fraud = int(y.sum())
        if n_fraud < args.cv_folds:
            raise ValueError(
                f"사기 건수({n_fraud})가 fold 수({args.cv_folds})보다 적습니다. "
                f"--cv-folds 를 줄이거나 데이터를 늘리세요."
            )
        print(f"\n[CV] {args.cv_folds}-fold  총 행: {len(X):,}  사기: {n_fraud}")
        metrics, pipe = run_cv(
            X, y, args.cv_folds, schema.imputer_strategy(), block_min, review_min
        )
        metrics["thresholds_file"] = str(args.thresholds) if args.thresholds.exists() else None
        metrics["block_min"] = block_min
        metrics["review_min"] = review_min

        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        print(f"\n지표 저장: {mpath}")

    # ── 홀드아웃 평가 ────────────────────────────────────────────────────────
    elif args.holdout_fraction is not None:
        ho = args.holdout_fraction
        if not (0 < ho < 1):
            raise ValueError("--holdout-fraction 은 0 초과 1 미만")

        n_fraud = int(y.sum())
        n_holdout_fraud = round(n_fraud * ho)
        if n_holdout_fraud < 10:
            print(
                f"\n[경고] 홀드아웃 예상 사기 건수 ≈ {n_holdout_fraud}건 — 지표 신뢰도 낮음. "
                f"--cv-folds 사용을 권장합니다."
            )

        X_tr, X_ho, y_tr, y_ho = train_test_split(
            X, y, test_size=ho, stratify=y, random_state=RANDOM_STATE
        )
        n_orig_train = len(X_tr)

        X_tr_clean, ho_imp = _impute_before_smote(X_tr.values, schema.imputer_strategy())
        X_ho_clean, _ = _impute_before_smote(X_ho.values, schema.imputer_strategy(), fitted_imp=ho_imp)

        smote = SMOTE(random_state=RANDOM_STATE)
        X_tr_sm, y_tr_sm = smote.fit_resample(X_tr_clean, y_tr.values)

        pipe = build_pipeline(schema.imputer_strategy())
        pipe.fit(X_tr_sm, y_tr_sm)

        proba = pipe.named_steps["clf"].predict_proba(X_ho_clean)[:, 1]
        yv = y_ho.values.astype(int)

        auc = float(roc_auc_score(yv, proba))
        pr = float(average_precision_score(yv, proba))
        q = _queue_metrics(yv, proba, block_min, review_min)

        metrics = {
            "eval_method": "stratified_holdout",
            "holdout_fraction": ho,
            "random_state": RANDOM_STATE,
            "n_train_original": n_orig_train,
            "n_train_after_smote": int(len(X_tr_sm)),
            "n_holdout": int(len(X_ho)),
            "n_holdout_fraud": int(yv.sum()),
            "holdout_fraud_rate": float(yv.mean()),
            "roc_auc_holdout": auc,
            "pr_auc_holdout": pr,
            "thresholds_file": str(args.thresholds) if args.thresholds.exists() else None,
            "block_min": block_min,
            "review_min": review_min,
            "holdout_queue_size_review_or_block": q["queue_size"],
            "holdout_recall_in_queue": q["recall_in_queue"],
            "holdout_fpr_in_queue_among_normal": q["fpr_in_queue"],
            "holdout_confusion_queue": q["confusion_queue"],
        }
        if n_holdout_fraud < 10:
            metrics["warning"] = (
                f"홀드아웃 사기 건수 {n_holdout_fraud}건 — ROC/PR-AUC 신뢰도 낮음 "
                f"(샘플 수 부족). --cv-folds 사용 권장."
            )

        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        print(f"\n지표 저장: {mpath}")

    # ── 평가 없이 전체 학습 ──────────────────────────────────────────────────
    else:
        X_clean, _ = _impute_before_smote(X.values, schema.imputer_strategy())
        smote = SMOTE(random_state=RANDOM_STATE)
        X_sm, y_sm = smote.fit_resample(X_clean, y.values)
        pipe = build_pipeline(schema.imputer_strategy())
        pipe.fit(X_sm, y_sm)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "pipeline": pipe,
        "schema_raw": schema.raw,
        "feature_names": schema.feature_columns(),
        "schema_path": str(args.schema.resolve()),
        "train_csv": str(args.train_csv.resolve()),
        "eval_method": (
            "cv" if args.cv_folds else
            "holdout" if args.holdout_fraction else
            "none"
        ),
    }
    joblib.dump(bundle, args.out)
    print(f"\n저장: {args.out}")
    print(f"  스키마: {schema.name} (v{schema.version})")
    print(f"  원본 학습 데이터: {len(X):,}행  특성 수: {X.shape[1]}")


if __name__ == "__main__":
    main()
