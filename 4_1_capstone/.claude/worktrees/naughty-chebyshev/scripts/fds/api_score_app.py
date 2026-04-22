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
import yaml

try:
    from fastapi import FastAPI, HTTPException
except ImportError as e:  # pragma: no cover
    raise SystemExit("FastAPI 필요: pip install -r requirements-fds-optional.txt") from e

FDS_DIR = Path(__file__).resolve().parent
ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from policy_merge import decide_from_score  # noqa: E402
from schema import FDSSchema  # noqa: E402
from scoring import score_prepared_frame  # noqa: E402

_bundle: dict[str, Any] | None = None
_bundle_path: Path = Path(
    os.environ.get("FDS_BUNDLE_PATH", str(ROOT / "outputs" / "fds" / "model_bundle_open_full.joblib"))
)
_thresholds: dict[str, Any] | None = None
_THRESHOLDS_PATH: Path = Path(
    os.environ.get(
        "FDS_THRESHOLDS_PATH",
        str(ROOT / "policies" / "fds" / "thresholds_v1.yaml"),
    )
)

_ACTION_MAP = {
    "PASS": "APPROVED",
    "REVIEW": "PENDING",
    "BLOCK": "DECLINED",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bundle, _thresholds
    p = Path(_bundle_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise RuntimeError(f"번들 없음: {p} (FDS_BUNDLE_PATH 또는 학습 후 경로 확인)")
    _bundle = joblib.load(p)

    tp = _THRESHOLDS_PATH if _THRESHOLDS_PATH.is_absolute() else ROOT / _THRESHOLDS_PATH
    if tp.exists():
        with tp.open(encoding="utf-8") as f:
            _thresholds = yaml.safe_load(f)
    else:
        _thresholds = {"block_min": 0.5, "review_min": 0.35}

    yield
    _bundle = None
    _thresholds = None


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


@app.post("/v1/authorize")
def authorize(row: dict[str, Any]) -> dict[str, Any]:
    """단일 거래 스코어링 + 정책 결정을 한 번에 처리.

    입력: V1-V30 필수, transaction_id 또는 ID 선택.
    출력: transaction_id, decision(APPROVED/PENDING/DECLINED), score, reason_codes, threshold_used.
    """
    assert _bundle is not None
    assert _thresholds is not None

    schema = FDSSchema.from_dict(_bundle["schema_raw"])

    # transaction_id 결정
    transaction_id = str(
        row.get("transaction_id") or row.get("ID") or "api_0"
    )

    # 스코어링 (score_batch 와 동일한 prepare_frame 경로 사용)
    df = _rows_to_frame([row])
    df = schema.prepare_frame(df)
    scored = score_prepared_frame(df, _bundle)
    result = scored.iloc[0]

    score_val: float = float(result["score"])
    reason_codes: str = str(result["reason_code"])

    # 정책 결정
    block_min = float(_thresholds.get("block_min", 0.5))
    review_min = float(_thresholds.get("review_min", 0.35))
    adjustments = _thresholds.get("adjustments")

    action = decide_from_score(
        score_val,
        block_min,
        review_min,
        adjustments=adjustments,
        row=row,
    )
    decision = _ACTION_MAP.get(action, action)

    return {
        "transaction_id": transaction_id,
        "decision": decision,
        "score": score_val,
        "reason_codes": reason_codes,
        "threshold_used": {"block_min": block_min, "review_min": review_min},
    }
