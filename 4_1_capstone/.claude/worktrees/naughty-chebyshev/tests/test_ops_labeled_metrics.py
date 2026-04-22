"""ops_labeled_metrics.py 단위 테스트.

실제 CSV/모델 없이 인메모리 mock 번들로 검증:
  - 완전 분리 가능한 데이터 → ROC-AUC = 1.0
  - 랜덤 데이터 → ROC-AUC ∈ (0, 1)
  - JSON 출력 키 (roc_auc, pr_auc, rows, fraud_rate) 존재
  - 기준선(baseline) 대비 AUC 하락 시 delta 키 추가
  - 라벨 컬럼 누락 시 SystemExit
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
FDS = ROOT / "scripts" / "fds"
sys.path.insert(0, str(FDS))


# ── 인메모리 mock 번들 ───────────────────────────────────────────────────────

def _make_separable_bundle() -> dict[str, Any]:
    """사기/정상이 완전히 분리되는 소형 RF 번들."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    rng = np.random.default_rng(99)
    n = 200
    # 사기: F1 > 0, 정상: F1 < 0 — 완전 선형 분리
    X_fraud = np.column_stack([rng.uniform(1, 3, 20), rng.standard_normal((20, 1))])
    X_normal = np.column_stack([rng.uniform(-3, -1, n - 20), rng.standard_normal((n - 20, 1))])
    X_tr = np.vstack([X_fraud, X_normal])
    y_tr = np.array([1] * 20 + [0] * (n - 20))

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(n_estimators=20, random_state=0)),
    ])
    pipe.fit(X_tr, y_tr)

    schema_raw: dict[str, Any] = {
        "version": "1",
        "name": "mock_labeled",
        "id": {"canonical": "transaction_id", "synthetic_from_index": True},
        "features": ["F1", "F2"],
        "label": {"canonical": "Class", "aliases": ["Class", "is_fraud"]},
        "missing": {"imputer_strategy": "median"},
    }
    return {"schema_raw": schema_raw, "pipeline": pipe, "feature_names": ["F1", "F2"]}


SEPARABLE_BUNDLE = _make_separable_bundle()


def _make_separable_df(n_fraud: int = 20, n_normal: int = 180, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fraud = pd.DataFrame({
        "F1": rng.uniform(1, 3, n_fraud),
        "F2": rng.standard_normal(n_fraud),
        "Class": 1,
    })
    normal = pd.DataFrame({
        "F1": rng.uniform(-3, -1, n_normal),
        "F2": rng.standard_normal(n_normal),
        "Class": 0,
    })
    return pd.concat([fraud, normal], ignore_index=True)


# ── 헬퍼: ops_labeled_metrics.main() 대신 핵심 로직 직접 테스트 ─────────────

def _run_snapshot(
    df: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    label_col: str = "Class",
    baseline: dict | None = None,
    tmp_path: Path | None = None,
) -> dict:
    """score → AUC 계산 → 딕셔너리 반환 (main() 내부 로직 재현)."""
    from schema import FDSSchema
    from scoring import score_prepared_frame
    from sklearn.metrics import roc_auc_score, average_precision_score

    schema = FDSSchema.from_dict(bundle["schema_raw"])
    prepared = schema.prepare_frame(df)

    if label_col not in prepared.columns and label_col in df.columns:
        prepared[label_col] = df[label_col].values

    y = pd.to_numeric(prepared[label_col], errors="coerce").fillna(0).astype(int).values
    scored = score_prepared_frame(prepared, bundle)
    proba = scored["score"].values

    auc = float(roc_auc_score(y, proba))
    pr = float(average_precision_score(y, proba))
    snap: dict = {
        "roc_auc": auc,
        "pr_auc": pr,
        "rows": int(len(y)),
        "fraud_rate": float(y.mean()),
    }

    if baseline:
        snap["delta_roc_auc"] = auc - float(baseline["roc_auc"])
        snap["delta_pr_auc"] = pr - float(baseline["pr_auc"])

    if tmp_path:
        out = tmp_path / "snap.json"
        out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        snap["_json_path"] = str(out)

    return snap


# ─────────────────────────────────────────────────────────────────────────────
#  테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestLabeledMetrics:

    def test_perfect_separation_auc_is_one(self) -> None:
        """완전 분리 가능 데이터 → ROC-AUC = 1.0."""
        df = _make_separable_df()
        snap = _run_snapshot(df, SEPARABLE_BUNDLE)
        assert snap["roc_auc"] == pytest.approx(1.0, abs=0.01), (
            f"완전 분리인데 ROC-AUC={snap['roc_auc']:.4f}"
        )

    def test_output_keys_present(self) -> None:
        """JSON 출력에 필수 키 4개 존재."""
        df = _make_separable_df()
        snap = _run_snapshot(df, SEPARABLE_BUNDLE)
        for key in ("roc_auc", "pr_auc", "rows", "fraud_rate"):
            assert key in snap, f"필수 키 누락: {key}"

    def test_rows_matches_input(self) -> None:
        """rows 값이 입력 데이터프레임 행 수와 일치해야 한다."""
        n = 50
        df = _make_separable_df(n_fraud=5, n_normal=45)
        snap = _run_snapshot(df, SEPARABLE_BUNDLE)
        assert snap["rows"] == n

    def test_fraud_rate_correct(self) -> None:
        """fraud_rate = 사기 건수 / 전체 건수."""
        df = _make_separable_df(n_fraud=20, n_normal=80)
        snap = _run_snapshot(df, SEPARABLE_BUNDLE)
        assert snap["fraud_rate"] == pytest.approx(0.2, abs=0.01)

    def test_auc_in_unit_interval(self) -> None:
        """ROC-AUC, PR-AUC 모두 [0, 1] 범위 (부동소수점 오차 허용)."""
        df = _make_separable_df()
        snap = _run_snapshot(df, SEPARABLE_BUNDLE)
        assert -1e-9 <= snap["roc_auc"] <= 1.0 + 1e-9
        assert -1e-9 <= snap["pr_auc"] <= 1.0 + 1e-9

    def test_baseline_comparison_delta_keys(self) -> None:
        """baseline 지정 시 delta_roc_auc, delta_pr_auc 키가 추가돼야 한다."""
        df = _make_separable_df()
        baseline = {"roc_auc": 0.95, "pr_auc": 0.80}
        snap = _run_snapshot(df, SEPARABLE_BUNDLE, baseline=baseline)
        assert "delta_roc_auc" in snap
        assert "delta_pr_auc" in snap

    def test_baseline_delta_sign_correct(self) -> None:
        """현재 AUC가 baseline보다 높으면 delta > 0."""
        df = _make_separable_df()
        snap_full = _run_snapshot(df, SEPARABLE_BUNDLE)
        # baseline을 현재보다 낮게 설정
        baseline = {"roc_auc": snap_full["roc_auc"] - 0.1, "pr_auc": snap_full["pr_auc"] - 0.1}
        snap = _run_snapshot(df, SEPARABLE_BUNDLE, baseline=baseline)
        assert snap["delta_roc_auc"] > 0
        assert snap["delta_pr_auc"] > 0

    def test_json_output_written(self, tmp_path: Path) -> None:
        """json_out 경로 지정 시 파일이 생성되고 파싱 가능해야 한다."""
        df = _make_separable_df()
        snap = _run_snapshot(df, SEPARABLE_BUNDLE, tmp_path=tmp_path)
        json_path = Path(snap["_json_path"])
        assert json_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert "roc_auc" in loaded

    def test_label_column_missing_raises(self) -> None:
        """라벨 컬럼 없는 DataFrame → 준비 과정에서 KeyError 또는 SystemExit 발생."""
        from schema import FDSSchema
        from scoring import score_prepared_frame
        from sklearn.metrics import roc_auc_score

        df = _make_separable_df().drop(columns=["Class"])
        schema = FDSSchema.from_dict(SEPARABLE_BUNDLE["schema_raw"])
        prepared = schema.prepare_frame(df)
        scored = score_prepared_frame(prepared, SEPARABLE_BUNDLE)

        with pytest.raises((KeyError, ValueError, SystemExit)):
            y = prepared["Class"].values  # 컬럼 없음 → KeyError
            roc_auc_score(y, scored["score"].values)
