"""규칙 YAML 평가 → 행별 rule_ids, rule_action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ACTION_TO_INT = {"PASS": 0, "REVIEW": 1, "BLOCK": 2}
INT_TO_ACTION = {0: "PASS", 1: "REVIEW", 2: "BLOCK"}


def load_rules(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_blocklist(path: Path, project_root: Path) -> set[str]:
    p = path if path.is_absolute() else project_root / path
    if not p.exists():
        return set()
    out: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.add(s)
    return out


def _eval_rule(df: pd.DataFrame, rule: dict[str, Any], project_root: Path) -> np.ndarray:
    n = len(df)
    mask = np.zeros(n, dtype=bool)

    if "blocklist_file" in rule:
        spec = rule["blocklist_file"]
        col = spec["column"]
        if col not in df.columns:
            return mask
        blk = _load_blocklist(Path(spec["path"]), project_root)
        if not blk:
            return mask
        mask = df[col].astype(str).isin(blk).values
        return mask

    if "amount_above" in rule:
        if rule.get("skip_if_no_amount") and "amount" not in df.columns:
            return mask
        if "amount" not in df.columns:
            return mask
        thr = float(rule["amount_above"])
        amt = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        mask = (amt > thr).values
        return mask

    if "column_in_values" in rule:
        spec = rule["column_in_values"]
        col = spec["column"]
        if rule.get("skip_if_missing_column", True) and col not in df.columns:
            return mask
        vals = {str(v) for v in (spec.get("values") or [])}
        if not vals:
            return mask
        mask = df[col].astype(str).isin(vals).values
        return mask

    return mask


def evaluate_rules(df: pd.DataFrame, rules_path: Path, project_root: Path) -> pd.DataFrame:
    cfg = load_rules(rules_path)
    rules = cfg.get("rules") or []
    n = len(df)
    row_sev = np.zeros(n, dtype=np.int8)
    ids_per_row: list[list[str]] = [[] for _ in range(n)]

    for rule in rules:
        rid = str(rule.get("id", "UNKNOWN"))
        action = str(rule.get("action", "PASS")).upper()
        sev = ACTION_TO_INT.get(action, 0)
        m = _eval_rule(df, rule, project_root)
        idxs = np.flatnonzero(m)
        for i in idxs:
            ids_per_row[i].append(rid)
            if sev > row_sev[i]:
                row_sev[i] = sev

    rule_ids = [";".join(sorted(set(x))) for x in ids_per_row]
    rule_action = [INT_TO_ACTION[int(s)] for s in row_sev]
    out = pd.DataFrame({"rule_ids": rule_ids, "rule_action": rule_action}, index=df.index)
    return out
