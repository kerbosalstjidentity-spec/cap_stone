"""배치 스코어링 코어 (batch_score / batch_run 공용)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from reason_codes import top_feature_reasons
from schema import FDSSchema


def score_prepared_frame(
    df_prepared: pd.DataFrame,
    bundle: dict[str, Any],
    *,
    top_reasons: int = 3,
) -> pd.DataFrame:
    """prepare_frame 이후 DataFrame → transaction_id, score, reason_code.

    단일 모델 번들과 앙상블 번들 모두 지원.
    앙상블 번들: bundle["ensemble"] == True 일 때 각 모델 확률의 평균 사용.
    reason_codes는 앙상블 시 첫 번째 RF 모델의 feature_importances_ 사용.
    """
    schema = FDSSchema.from_dict(bundle["schema_raw"])
    feature_names: list[str] = list(bundle["feature_names"])

    X_df = schema.feature_matrix(df_prepared)
    if list(X_df.columns) != feature_names:
        raise ValueError("입력 특성 열이 번들과 일치하지 않습니다.")

    X = X_df.values.astype(float)

    # ── 앙상블 번들 분기 ─────────────────────────────────────────────────────
    if bundle.get("ensemble") is True:
        models: list[dict[str, Any]] = bundle["models"]
        proba_list: list[np.ndarray] = []
        rf_pipe_for_reasons = None

        for model_entry in models:
            pipe = model_entry["pipeline"]
            X_t_m = pipe.named_steps["imputer"].transform(X)
            proba_list.append(pipe.named_steps["clf"].predict_proba(X_t_m)[:, 1])
            # reason_codes용: 첫 번째 RF 파이프라인 사용
            if rf_pipe_for_reasons is None and model_entry.get("name") == "rf":
                rf_pipe_for_reasons = pipe

        proba = np.mean(proba_list, axis=0)

        # reason_codes: RF 모델의 feature_importances_ 사용
        if rf_pipe_for_reasons is not None:
            X_t_rf = rf_pipe_for_reasons.named_steps["imputer"].transform(X)
            clf_rf = rf_pipe_for_reasons.named_steps["clf"]
            importances = getattr(clf_rf, "feature_importances_", None)
        else:
            X_t_rf = X
            importances = None

        if importances is None:
            reasons = [""] * len(df_prepared)
        else:
            reasons = top_feature_reasons(
                X_t_rf,
                feature_names,
                importances,
                top_k=top_reasons,
            )

    # ── 단일 모델 번들 (기존 코드 유지) ─────────────────────────────────────
    else:
        pipe = bundle["pipeline"]
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
    logger.info("Score quantiles (p50/p95/p99): %s", np.quantile(proba, [0.5, 0.95, 0.99]))

    # reason_code: 전역 중요도 × 배치 내 편차 기반 근사값.
    # SHAP 기반 정밀 설명은 ops_shap_sample.py 참고.
    return pd.DataFrame(
        {
            "transaction_id": df_prepared["transaction_id"].astype(str),
            "score": proba.astype(float),
            "reason_code": reasons,
            "reason_method": "importance_x_deviation",
        }
    )
