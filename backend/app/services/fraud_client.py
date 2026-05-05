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


async def mirror_audit_to_fraud(entry: dict) -> bool:
    """W3-#2: backend 감사 로그를 fraud-service blockchain audit chain 에 미러링.

    fraud-service 가 단일 정본 (해시 체인 + JSONL append) 이고, backend 는 PG 캐시로 운영.
    네트워크 실패 시 best-effort — backend 트랜잭션은 차단되지 않음.
    """
    url = f"{settings.FRAUD_SERVICE_URL}/v1/audit/append"
    payload = {
        "transaction_id": entry.get("transaction_id", ""),
        "user_id": entry.get("user_id", ""),
        "action": entry.get("action", ""),
        "score": float(entry.get("score", 0.0)),
        "rule_ids": entry.get("rule_ids", []),
        "reason_code": entry.get("reason", "")[:128],
        "amount": float(entry.get("amount", 0.0)),
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code in (200, 201)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        return False


async def fetch_fraud_score(features: dict) -> dict | None:
    """fraud-service 에서 ML 스코어링 수행.

    Args:
        features: 운영 모델(domain) 에 따라 다름.
            - paysim (W5.5-#8 이후 기본): {type, amount, oldbalanceOrg,
              newbalanceOrig, oldbalanceDest, newbalanceDest, nameDest, step}
            - open (레거시): V1~V30 PCA 익명 피처

    Returns:
        paysim: {fraud_probability, rf_probability, anomaly_score,
                 anomaly_normalized, reason_code, domain="paysim"}
        open  : {fraud_probability, xgb_probability, anomaly_score,
                 reason_code}
        연결 실패 시 None.
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
