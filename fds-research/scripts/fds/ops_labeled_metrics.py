"""
라벨이 있는 CSV에 대해 스코어 후 ROC-AUC·PR-AUC 계산 — 드리프트 모니터링용 스냅샷.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FDS_DIR))

from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="라벨 구간 AUC/PR-AUC 스냅샷")
    p.add_argument("--schema", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True, help="라벨 컬럼 포함 CSV")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--label-col", type=str, default="Class")
    p.add_argument("--baseline-json", type=Path, default=None, help="이전 스냅샷과 비교")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--targets", type=Path, default=Path("policies/fds/ops_targets_v1.yaml"))
    p.add_argument("--fail-on-alert", action="store_true")
    args = p.parse_args()

    schema = FDSSchema.from_yaml(args.schema)
    bundle = joblib.load(args.bundle)
    df = pd.read_csv(args.input)
    if args.label_col not in df.columns:
        raise SystemExit(f"라벨 컬럼 없음: {args.label_col}")

    df = schema.prepare_frame(df)
    y = pd.to_numeric(df[args.label_col], errors="coerce").fillna(0).astype(int).values
    scored = score_prepared_frame(df, bundle)
    proba = scored["score"].values

    auc = float(roc_auc_score(y, proba))
    pr = float(average_precision_score(y, proba))
    snap = {"roc_auc": auc, "pr_auc": pr, "rows": int(len(y)), "fraud_rate": float(y.mean())}
    print(json.dumps(snap, indent=2, ensure_ascii=False))

    alerts = 0
    if args.baseline_json and args.baseline_json.exists():
        import yaml

        base = json.loads(args.baseline_json.read_text(encoding="utf-8"))
        b_auc = float(base["roc_auc"])
        b_pr = float(base["pr_auc"])
        d_auc = auc - b_auc
        d_pr = pr - b_pr
        snap["delta_roc_auc"] = d_auc
        snap["delta_pr_auc"] = d_pr

        auc_thr = 0.05
        pr_thr = 0.05
        if args.targets.exists():
            with args.targets.open(encoding="utf-8") as f:
                tcfg = yaml.safe_load(f)
            dr = (tcfg.get("drift") or {})
            auc_thr = float(dr.get("auc_drop_alert", auc_thr))
            pr_thr = float(dr.get("pr_auc_drop_alert", pr_thr))
        if d_auc < -auc_thr:
            snap["roc_auc_drop_alert"] = True
            alerts += 1
        if d_pr < -pr_thr:
            snap["pr_auc_drop_alert"] = True
            alerts += 1

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.fail_on_alert and alerts > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
