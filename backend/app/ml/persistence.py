"""W6-#1 — 모델 영속화 (joblib.dump + 부팅 시 자동 로드).

train_all() 결과를 디스크에 박제해 컨테이너 재시작 시에도 학습 상태 유지.

저장 경로 (env 로 오버라이드 가능):
- ``ML_BUNDLE_DIR`` (기본 ``backend/_ml_bundles/``)

각 모델별 파일:
- ``cluster.joblib``   — KMeans + 학습된 카테고리 컬럼 순서
- ``anomaly.joblib``   — IsolationForest + scaler
- ``classifier.joblib``— XGBoost 모델 + 메타
- ``forecaster.pt``    — torch state_dict + scaler 스칼라

LSTM 은 torch state_dict 형태로 저장하기 위해 별도 처리.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _bundle_dir() -> Path:
    raw = os.environ.get("ML_BUNDLE_DIR", "")
    if raw:
        p = Path(raw)
    else:
        # 기본: 본 모듈 기준 backend/_ml_bundles/
        p = Path(__file__).resolve().parents[2] / "_ml_bundles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_dump(obj: Any, path: Path) -> bool:
    try:
        import joblib
    except ImportError:  # pragma: no cover
        logger.warning("joblib 미설치 — %s 저장 건너뜀", path.name)
        return False
    try:
        joblib.dump(obj, path)
        return True
    except Exception as exc:
        logger.warning("dump 실패 (%s): %s", path.name, exc)
        return False


def _safe_load(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        import joblib
    except ImportError:  # pragma: no cover
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("load 실패 (%s): %s", path.name, exc)
        return None


def dump_all_models() -> dict[str, bool]:
    """현재 메모리 싱글턴들 디스크 저장. 호출 결과 dict 로 어떤 모델이 성공했는지."""
    from app.ml.anomaly import anomaly_detector
    from app.ml.classifier import overspend_classifier
    from app.ml.clustering import cluster_model
    from app.ml.forecasting import TORCH_AVAILABLE, forecaster

    d = _bundle_dir()
    out: dict[str, bool] = {}
    out["cluster"] = _safe_dump(
        {
            "model": cluster_model.model,
            "n_clusters": cluster_model.n_clusters,
            "is_trained": getattr(cluster_model, "is_trained", True),
        },
        d / "cluster.joblib",
    )
    out["anomaly"] = _safe_dump(
        {"model": anomaly_detector.model, "is_trained": getattr(anomaly_detector, "is_trained", True)},
        d / "anomaly.joblib",
    )
    out["classifier"] = _safe_dump(
        {"model": overspend_classifier.model, "is_trained": getattr(overspend_classifier, "is_trained", False)},
        d / "classifier.joblib",
    )
    # LSTM 은 torch state_dict 별도
    if TORCH_AVAILABLE and forecaster.is_trained and forecaster.model is not None:
        try:
            import torch
            torch.save(
                {
                    "state_dict": forecaster.model.state_dict(),
                    "scaler_mean": forecaster._scaler_mean,
                    "scaler_std": forecaster._scaler_std,
                    "seq_length": forecaster.seq_length,
                    "is_trained": True,
                },
                d / "forecaster.pt",
            )
            out["forecaster"] = True
        except Exception as exc:
            logger.warning("forecaster 저장 실패: %s", exc)
            out["forecaster"] = False
    else:
        out["forecaster"] = False
    return out


def load_all_models() -> dict[str, bool]:
    """부팅 시 호출. 디스크에서 읽어 싱글턴에 주입. 파일 없으면 무시(원래 fallback 유지)."""
    from app.ml.anomaly import anomaly_detector
    from app.ml.classifier import overspend_classifier
    from app.ml.clustering import cluster_model
    from app.ml.forecasting import TORCH_AVAILABLE, forecaster

    d = _bundle_dir()
    out: dict[str, bool] = {}

    cluster = _safe_load(d / "cluster.joblib")
    if cluster is not None and cluster.get("model") is not None:
        cluster_model.model = cluster["model"]
        if hasattr(cluster_model, "is_trained"):
            cluster_model.is_trained = bool(cluster.get("is_trained", False))
        out["cluster"] = True
    else:
        out["cluster"] = False

    anomaly = _safe_load(d / "anomaly.joblib")
    if anomaly is not None and anomaly.get("model") is not None:
        anomaly_detector.model = anomaly["model"]
        out["anomaly"] = True
    else:
        out["anomaly"] = False

    classifier = _safe_load(d / "classifier.joblib")
    if classifier is not None and classifier.get("model") is not None:
        overspend_classifier.model = classifier["model"]
        if hasattr(overspend_classifier, "is_trained"):
            overspend_classifier.is_trained = bool(classifier.get("is_trained", True))
        out["classifier"] = True
    else:
        out["classifier"] = False

    forecaster_path = d / "forecaster.pt"
    if TORCH_AVAILABLE and forecaster_path.is_file() and forecaster.model is not None:
        try:
            import torch
            ckpt = torch.load(forecaster_path, map_location="cpu", weights_only=False)
            forecaster.model.load_state_dict(ckpt["state_dict"])
            forecaster._scaler_mean = ckpt.get("scaler_mean", 0.0)
            forecaster._scaler_std = ckpt.get("scaler_std", 1.0) or 1.0
            forecaster.is_trained = bool(ckpt.get("is_trained", True))
            out["forecaster"] = True
        except Exception as exc:
            logger.warning("forecaster 로드 실패: %s", exc)
            out["forecaster"] = False
    else:
        out["forecaster"] = False

    return out


def bundle_paths() -> dict[str, str]:
    d = _bundle_dir()
    return {
        "cluster": str(d / "cluster.joblib"),
        "anomaly": str(d / "anomaly.joblib"),
        "classifier": str(d / "classifier.joblib"),
        "forecaster": str(d / "forecaster.pt"),
        "dir": str(d),
    }
