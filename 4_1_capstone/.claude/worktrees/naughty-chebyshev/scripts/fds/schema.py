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

    # ── 스키마 YAML 구조 검증 ─────────────────────────────────────────────────

    @staticmethod
    def validate_schema_raw(raw: dict[str, Any], source: str = "<dict>") -> None:
        """스키마 YAML 딕셔너리의 필수 구조를 검증한다.

        오류 조건:
        - `version` 키 누락
        - `features` 키 누락 또는 빈 리스트
        - `features` 값이 리스트가 아닌 경우

        Parameters
        ----------
        raw:
            yaml.safe_load() 결과 딕셔너리
        source:
            오류 메시지에 표시할 출처 정보 (파일 경로 등)

        Raises
        ------
        ValueError
            구조 오류 발견 시
        """
        if not raw or not isinstance(raw, dict):
            raise ValueError(f"[{source}] 스키마 YAML이 비어 있거나 딕셔너리가 아닙니다.")
        if "version" not in raw:
            raise ValueError(f"[{source}] 필수 키 'version' 누락.")
        feats = raw.get("features")
        if feats is None:
            raise ValueError(f"[{source}] 필수 키 'features' 누락.")
        if not isinstance(feats, list):
            raise ValueError(
                f"[{source}] 'features'는 리스트여야 합니다. 현재 타입: {type(feats).__name__}"
            )
        if len(feats) == 0:
            raise ValueError(f"[{source}] 'features' 리스트가 비어 있습니다.")

    @classmethod
    def from_yaml(cls, path: Path) -> FDSSchema:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cls.validate_schema_raw(raw, source=str(path))
        return cls(version=str(raw["version"]), name=str(raw.get("name", path.stem)), raw=raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FDSSchema:
        cls.validate_schema_raw(raw, source="<embedded>")
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
