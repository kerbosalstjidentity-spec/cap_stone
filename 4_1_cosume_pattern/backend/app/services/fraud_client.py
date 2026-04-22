"""fraud-service REST 연동 클라이언트.

fraud-service (port 8010)의 사용자 프로필을 가져와
소비 분석에 보조 데이터로 활용.
"""

import httpx

from app.config import settings


async def fetch_fraud_profile(user_id: str) -> dict | None:
    """fraud-service에서 사용자 프로필 조회.

    Returns:
        {tx_count, avg_amount, max_amount, peak_hour, merchant_diversity, velocity}
        또는 연결 실패 시 None
    """
    url = f"{settings.FRAUD_SERVICE_URL}/v1/profile/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return None


async def fetch_fraud_score(features: dict) -> dict | None:
    """fraud-service에서 ML 스코어링 수행.

    Args:
        features: V1~V30 dict

    Returns:
        {fraud_probability, xgb_probability, anomaly_score, reason_code}
        또는 연결 실패 시 None
    """
    url = f"{settings.FRAUD_SERVICE_URL}/v1/score"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"features": features})
            if resp.status_code == 200:
                return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return None
