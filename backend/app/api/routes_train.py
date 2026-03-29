"""ML 모델 학습 API 엔드포인트."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.ml.trainer import train_all

router = APIRouter(prefix="/v1/ml", tags=["ml-training"])


@router.post("/train")
async def trigger_training(session: AsyncSession = Depends(get_session)):
    """모든 ML 모델 학습/재학습 트리거.

    Returns:
        각 모델별 학습 결과 요약
    """
    results = await train_all(session)
    return {"message": "ML training complete", "results": results}


@router.get("/status")
async def model_status():
    """현재 ML 모델 학습 상태 확인."""
    from app.ml.anomaly import anomaly_detector
    from app.ml.classifier import overspend_classifier
    from app.ml.clustering import cluster_model
    from app.ml.forecasting import forecaster

    return {
        "clustering": {"is_fitted": cluster_model.is_fitted},
        "anomaly": {"is_fitted": anomaly_detector.is_fitted},
        "classifier": {"is_fitted": overspend_classifier.is_fitted},
        "forecaster": {"is_trained": forecaster.is_trained},
    }
