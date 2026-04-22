"""
참조 CSV vs 현재 CSV 수치 특성 비교 — PSI, 평균 편차(σ). ops_targets_v1 알람과 비교 가능.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    exp = expected[~np.isnan(expected.astype(float))]
    act = actual[~np.isnan(actual.astype(float))]
    if len(exp) < buckets * 2 or len(act) < buckets * 2:
        return float("nan")
    qs = np.unique(np.quantile(exp, np.linspace(0, 1, buckets + 1)))
    if len(qs) < 3:
        return float("nan")
    exp_hist, _ = np.histogram(exp, bins=qs)
    act_hist, _ = np.histogram(act, bins=qs)
    exp_pct = np.clip(exp_hist / max(exp_hist.sum(), 1), 1e-6, 1.0)
    act_pct = np.clip(act_hist / max(act_hist.sum(), 1), 1e-6, 1.0)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def main() -> None:
    p = argparse.ArgumentParser(description="특성 분포 드리프트(PSI·평균σ)")
    p.add_argument("--ref", type=Path, required=True)
    p.add_argument("--current", type=Path, required=True)
    p.add_argument("--ref-nrows", type=int, default=None)
    p.add_argument("--current-nrows", type=int, default=None)
    p.add_argument(
        "--columns",
        type=str,
        default=None,
        help="쉼표 구분 특성명. 미지정 시 양쪽 공통의 수치형 V*·Amount 등",
    )
    p.add_argument("--targets", type=Path, default=Path("policies/fds/ops_targets_v1.yaml"))
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--fail-on-alert", action="store_true", help="PSI/σ 알람 시 종료코드 1")
    args = p.parse_args()

    ref = pd.read_csv(args.ref, nrows=args.ref_nrows)
    cur = pd.read_csv(args.current, nrows=args.current_nrows)

    if args.columns:
        cols = [c.strip() for c in args.columns.split(",") if c.strip()]
    else:
        common = [c for c in ref.columns if c in cur.columns]
        skip = {"class", "id", "time", "transaction_id", "isfraud"}
        cols = []
        for c in common:
            if c.lower() in skip or c in ("Class", "ID"):
                continue
            if pd.api.types.is_numeric_dtype(ref[c]) or pd.api.types.is_numeric_dtype(cur[c]):
                cols.append(c)

    psi_alert = 0.25
    sigma_alert = 3.0
    if args.targets.exists():
        with args.targets.open(encoding="utf-8") as f:
            tcfg: dict[str, Any] = yaml.safe_load(f)
        mon = tcfg.get("monitoring") or {}
        psi_alert = float(mon.get("score_distribution_shift_psi_alert", psi_alert))
        sigma_alert = float(mon.get("mean_shift_sigma_alert", sigma_alert))

    rows: list[dict[str, Any]] = []
    alerts = 0
    for c in cols:
        a = pd.to_numeric(ref[c], errors="coerce").dropna().values
        b = pd.to_numeric(cur[c], errors="coerce").dropna().values
        if len(a) < 10 or len(b) < 10:
            continue
        psi_v = _psi(a, b)
        mu_a, sd_a = float(np.mean(a)), float(np.std(a, ddof=0))
        mu_b = float(np.mean(b))
        sd = max(sd_a, 1e-9)
        zshift = abs(mu_b - mu_a) / sd
        row = {"column": c, "psi": psi_v, "mean_shift_sigma": zshift}
        if not np.isnan(psi_v) and psi_v >= psi_alert:
            row["psi_alert"] = True
            alerts += 1
        else:
            row["psi_alert"] = False
        if zshift >= sigma_alert:
            row["sigma_alert"] = True
            alerts += 1
        else:
            row["sigma_alert"] = False
        rows.append(row)

    out = {"columns_checked": len(rows), "per_column": rows, "alert_count": alerts}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.fail_on_alert and alerts > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
