"""
RF 번들에 대해 소량 행 TreeExplainer SHAP 요약 (선택 의존성 shap).

  pip install -r requirements-fds-optional.txt
  py -3 scripts/fds/ops_shap_sample.py --bundle outputs/fds/model_bundle_open_full.joblib --input data/fds/mock_transactions_v2.csv --nrows 100
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FDS_DIR = Path(__file__).resolve().parent
ROOT = FDS_DIR.parents[1]
sys.path.insert(0, str(FDS_DIR))

from schema import FDSSchema  # noqa: E402


def main() -> None:
    try:
        import shap
    except ImportError:
        raise SystemExit("shap 미설치: pip install -r requirements-fds-optional.txt")

    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--nrows", type=int, default=150)
    p.add_argument("--out", type=Path, default=ROOT / "outputs" / "fds" / "shap_mean_abs_sample.csv")
    args = p.parse_args()

    bundle = joblib.load(args.bundle)
    schema = FDSSchema.from_dict(bundle["schema_raw"])

    df = pd.read_csv(args.input, nrows=args.nrows)
    df = schema.prepare_frame(df)
    X_df = schema.feature_matrix(df)
    names = list(bundle["feature_names"])
    pipe = bundle["pipeline"]
    X = X_df[names].values.astype(float)
    X_t = pipe.named_steps["imputer"].transform(X)
    clf = pipe.named_steps["clf"]

    explainer = shap.TreeExplainer(clf)
    sv = explainer.shap_values(X_t)
    if isinstance(sv, list):
        # 이진 분류: 양성 클래스 쪽 사용
        sv = sv[1] if len(sv) > 1 else sv[0]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        # (샘플, 특성, 클래스)
        sv = sv[:, :, 1] if sv.shape[2] > 1 else sv[:, :, 0]
    mean_abs = np.mean(np.abs(sv), axis=0).ravel()
    out_df = pd.DataFrame({"feature": names, "mean_abs_shap": mean_abs}).sort_values(
        "mean_abs_shap", ascending=False
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"저장: {args.out}")
    print(out_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
