"""
검증 확률에 대한 임계값 탐색, PR/캘리브레이션 곡선 내보내기.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


def threshold_scan(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    thresholds: np.ndarray | None = None,
    betas: tuple[float, ...] = (0.5, 1.0, 2.0),
    min_recall: float = 0.2,
    fp_cost: float = 1.0,
    fn_cost: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    임계값 스윕 + Fβ 최대, 재현율 하한, 비용(fp_cost*FP + fn_cost*FN) 최소에 가까운 threshold.
    반환: (per_threshold 상세, best 요약 1행씩)
    """
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    if thresholds is None:
        thresholds = np.linspace(0.001, 0.999, 499)

    rows = []
    for t in thresholds:
        pred = (y_prob >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        fn = int(((pred == 0) & (y_true == 1)).sum())
        tn = int(((pred == 0) & (y_true == 0)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        cost = fp_cost * fp + fn_cost * fn
        row = {
            "threshold": t,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "cost": cost,
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "TN": tn,
        }
        for beta in betas:
            b2 = beta**2
            fbeta = (1 + b2) * prec * rec / (b2 * prec + rec) if (b2 * prec + rec) else 0.0
            row[f"f_beta_{beta}"] = fbeta
        rows.append(row)

    detail = pd.DataFrame(rows)

    best_rows = []
    for beta in betas:
        col = f"f_beta_{beta}"
        idx = detail[col].idxmax()
        r = detail.loc[idx].to_dict()
        r["criterion"] = f"max_f_beta_{beta}"
        best_rows.append(r)

    idx_cost = detail["cost"].idxmin()
    r = detail.loc[idx_cost].to_dict()
    r["criterion"] = "min_cost"
    best_rows.append(r)

    rec_ok = detail[detail["recall"] >= min_recall]
    if len(rec_ok):
        idx_f1 = rec_ok["f1"].idxmax()
        r = detail.loc[idx_f1].to_dict()
        r["criterion"] = f"max_f1_recall>={min_recall}"
        best_rows.append(r)

    summary = pd.DataFrame(best_rows)
    return detail, summary


def export_pr_curve(y_true: np.ndarray, y_prob: np.ndarray, path: Path) -> None:
    precision, recall, thr = precision_recall_curve(y_true, y_prob)
    # len(precision)==len(recall)==len(thr)+1
    out = pd.DataFrame(
        {
            "precision": precision[:-1],
            "recall": recall[:-1],
            "threshold": thr,
        }
    )
    out = pd.concat(
        [out, pd.DataFrame([{"precision": precision[-1], "recall": recall[-1], "threshold": np.nan}])],
        ignore_index=True,
    )
    out.to_csv(path, index=False, encoding="utf-8-sig")


def export_calibration_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    path: Path,
    *,
    n_bins: int = 10,
) -> None:
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
    pd.DataFrame({"mean_predicted_prob": prob_pred, "fraction_positives": prob_true}).to_csv(
        path, index=False, encoding="utf-8-sig"
    )


def classification_metrics_at_threshold(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float
) -> dict:
    pred = (y_prob >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    return {
        "threshold": threshold,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "precision": tp / (tp + fp) if (tp + fp) else 0.0,
        "recall": tp / (tp + fn) if (tp + fn) else 0.0,
        "roc_auc": roc_auc_score(y_true, y_prob),
        "pr_auc": average_precision_score(y_true, y_prob),
    }
