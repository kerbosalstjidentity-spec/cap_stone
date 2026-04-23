"""FDS 스키마 v1 로더·검증 (YAML)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass
class FDSSchema:
    version: str
    name: str
    raw: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: Path) -> FDSSchema:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not raw or "version" not in raw:
            raise ValueError(f"유효하지 않은 스키마 YAML: {path}")
        return cls(version=str(raw["version"]), name=str(raw.get("name", path.stem)), raw=raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FDSSchema:
        return cls(version=str(raw["version"]), name=str(raw.get("name", "embedded")), raw=raw)

    def _first_present(self, df: pd.DataFrame, aliases: list[str]) -> str | None:
        for a in aliases:
            if a in df.columns:
                return a
        return None

    def _id_config(self) -> dict[str, Any]:
        return self.raw.get("id") or {}

    def _label_config(self) -> dict[str, Any]:
        return self.raw.get("label") or {}

    def prepare_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """별칭 해석·필수 컬럼 검증·(옵션) 합성 transaction_id."""
        out = df.copy()

        # 데이터 누수 방지: 식별자 컬럼 제거
        out = out.drop(columns=['customer_id', 'ip_address'], errors='ignore')

        id_cfg = self._id_config()
        aliases = [id_cfg.get("canonical", "transaction_id")]
        aliases.extend(id_cfg.get("aliases") or [])

        if id_cfg.get("synthetic_from_index"):
            prefix = str(id_cfg.get("synthetic_prefix") or "txn_")
            out["transaction_id"] = prefix + out.index.astype(str)
        else:
            col = self._first_present(out, aliases)
            if col is None:
                raise ValueError(f"ID 컬럼 없음. 기대 별칭: {aliases}")
            if col != "transaction_id":
                out["transaction_id"] = out[col].astype(str)

        feats = self.raw.get("features") or []
        missing = [c for c in feats if c not in out.columns]
        if missing:
            raise ValueError(f"스키마 특성 누락: {missing[:10]}{'...' if len(missing) > 10 else ''}")

        for block in ("event_ts", "amount"):
            cfg = self.raw.get(block)
            if not cfg:
                continue
            req = bool(cfg.get("required"))
            als = [cfg.get("canonical", block)] + list(cfg.get("aliases") or [])
            found = self._first_present(out, als)
            if req and found is None:
                raise ValueError(f"필수 컬럼 없음: {block} (별칭 {als})")
            if found and found != cfg.get("canonical", block):
                out[cfg.get("canonical", block)] = out[found]

        return out

    def feature_columns(self) -> list[str]:
        return list(self.raw.get("features") or [])

    def feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = self.feature_columns()
        return df[cols].copy()

    def labels_if_any(self, df: pd.DataFrame) -> pd.Series | None:
        cfg = self._label_config()
        als = [cfg.get("canonical", "is_fraud")] + list(cfg.get("aliases") or [])
        col = self._first_present(df, als)
        if col is None:
            return None
        y = df[col]
        if y.dtype == object:
            y = pd.to_numeric(y, errors="coerce").fillna(0).astype(int)
        else:
            y = y.astype(int)
        return y

    def imputer_strategy(self) -> str:
        miss = self.raw.get("missing") or {}
        return str(miss.get("imputer_strategy") or "median")
