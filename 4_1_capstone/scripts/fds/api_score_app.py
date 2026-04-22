"""
준실시간 스코어 API (프로토타입).

  set FDS_BUNDLE_PATH=outputs/fds/model_bundle_open_full.joblib
  py -3 -m uvicorn scripts.fds.api_score_app:app --host 127.0.0.1 --port 8765

요청 본문: V1..V30 필수, ID 또는 transaction_id 선택.
의존성: pip install -r requirements-fds-optional.txt
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

try:
    from fastapi import FastAPI, HTTPException
except ImportError as e:  # pragma: no cover
    raise SystemExit("FastAPI 필요: pip install -r requirements-fds-optional.txt") from e

FDS_DIR = Path(__file__).resolve().parent
ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402

_bundle: dict[str, Any] | None = None
_bundle_path: Path = Path(
    os.environ.get("FDS_BUNDLE_PATH", str(ROOT / "outputs" / "fds" / "model_bundle_open_full.joblib"))
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bundle
    p = Path(_bundle_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise RuntimeError(f"번들 없음: {p} (FDS_BUNDLE_PATH 또는 학습 후 경로 확인)")
    _bundle = joblib.load(p)
    yield
    _bundle = None


app = FastAPI(title="FDS Batch Score API (proto)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "bundle": str(_bundle_path)}


def _rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        raise HTTPException(400, "빈 배열")
    feat = [f"V{i}" for i in range(1, 31)]
    out_rows = []
    for i, raw in enumerate(rows):
        r = dict(raw)
        if "ID" not in r and "transaction_id" not in r:
            r["ID"] = f"api_{i}"
        miss = [f for f in feat if f not in r]
        if miss:
            raise HTTPException(400, detail=f"행 {i}: 누락 특성 {miss[:6]}")
        out_rows.append(r)
    return pd.DataFrame(out_rows)


@app.post("/v1/score/batch")
def score_batch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert _bundle is not None
    schema = FDSSchema.from_dict(_bundle["schema_raw"])
    df = _rows_to_frame(rows)
    df = schema.prepare_frame(df)
    scored = score_prepared_frame(df, _bundle)
    return scored.to_dict(orient="records")


@app.post("/v1/score/single")
def score_single(row: dict[str, Any]) -> dict[str, Any]:
    out = score_batch([row])
    return out[0]
