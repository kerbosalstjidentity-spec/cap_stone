"""배치 스코어링 코어 (batch_score / batch_run 공용)."""

from __future__ import annotations

from typing import Any

import logging
import numpy as np
import pandas as pd

from reason_codes import top_feature_reasons
from schema import FDSSchema


def score_prepared_frame(
    df_prepared: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    top_reasons: int = 3,
) -> pd.DataFrame:
    """prepare_frame 이후 DataFrame → transaction_id, score, reason_code."""
    schema = FDSSchema.from_dict(bundle["schema_raw"])
    pipe = bundle["pipeline"]
    feature_names: list[str] = list(bundle["feature_names"])

    X_df = schema.feature_matrix(df_prepared)
    if list(X_df.columns) != feature_names:
        raise ValueError("입력 특성 열이 번들과 일치하지 않습니다.")

    X = X_df.values.astype(float)
    X_t = pipe.named_steps["imputer"].transform(X)
    proba = pipe.named_steps["clf"].predict_proba(X_t)[:, 1]

    clf = pipe.named_steps["clf"]
    importances = getattr(clf, "feature_importances_", None)
    if importances is None:
        reasons = [""] * len(df_prepared)
    else:
        reasons = top_feature_reasons(
            X_t,
            feature_names,
            importances,
            top_k=top_reasons,
        )

    # 스코어 분포 로깅 (모니터링)
    logging.info(f"Score quantiles: {np.quantile(proba, [0.5, 0.95, 0.99])}")

    return pd.DataFrame(
        {
            "transaction_id": df_prepared["transaction_id"].astype(str),
            "score": proba.astype(float),
            "reason_code": reasons,
        }
    )
