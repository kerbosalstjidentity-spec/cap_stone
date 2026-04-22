from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_health import router as health_router
from app.api.routes_score import router as score_router
from app.api.routes_fraud import router as fraud_router
from app.api.routes_profile import router as profile_router
from app.api.routes_simulate import router as simulate_router
from app.api.routes_audit import router as audit_router
from app.api.routes_intelligence import router as intelligence_router
from app.kafka import producer as kafka_producer
from app.kafka import consumer as kafka_consumer
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.api_key import ApiKeyMiddleware
from app.middleware.abe_auth import AbeAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await kafka_producer.start_producer()
    await kafka_consumer.start_consumer()
    yield
    await kafka_consumer.stop_consumer()
    await kafka_producer.stop_producer()


app = FastAPI(
    title="Fraud scoring API",
    description="캡스톤 연구와 분리한 추론 서비스",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(ApiKeyMiddleware)
app.add_middleware(AbeAuthMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(score_router, prefix="/v1", tags=["score"])
app.include_router(fraud_router, prefix="/v1/fraud", tags=["fraud"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(profile_router, prefix="/v1/profile", tags=["profile"])
app.include_router(simulate_router, prefix="/v1/simulate", tags=["simulate"])
app.include_router(audit_router, prefix="/v1/audit", tags=["audit"])
app.include_router(intelligence_router, prefix="/v1/intelligence", tags=["intelligence"])


@app.get("/")
def root():
    return {
        "service": "fraud-service",
        "docs": "/docs",
        "admin": "/admin",
    }
