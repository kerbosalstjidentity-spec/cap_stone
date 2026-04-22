from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

router = APIRouter()


def _check_model() -> dict[str, Any]:
    try:
        from app.scoring.model_loader import load_model_bundle, resolve_model_path
        from app.config import settings
        path = resolve_model_path(settings.model_path)
        bundle = load_model_bundle(path)
        return {"status": "ok", "model_path": str(path)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_redis() -> dict[str, Any]:
    if os.getenv("PROFILE_STORE", "memory").lower() != "redis":
        return {"status": "disabled"}
    try:
        import redis as redis_lib
        r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        return {"status": "ok"}
    except ImportError:
        return {"status": "disabled", "detail": "redis-py 미설치"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_kafka() -> dict[str, Any]:
    try:
        import aiokafka  # noqa: F401
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        from app.kafka import consumer as kc
        running = kc._consumer_task is not None and not kc._consumer_task.done()
        return {"status": "ok" if running else "stopped", "bootstrap": bootstrap}
    except ImportError:
        return {"status": "disabled", "detail": "aiokafka 미설치"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_firebase() -> dict[str, Any]:
    enabled = os.getenv("FIREBASE_ENABLED", "false").lower() == "true"
    if not enabled:
        return {"status": "disabled"}
    try:
        import firebase_admin
        initialized = bool(firebase_admin._apps)
        return {"status": "ok" if initialized else "not_initialized"}
    except ImportError:
        return {"status": "disabled", "detail": "firebase-admin 미설치"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("")
def health():
    return {"status": "ok"}


@router.get("/detail")
def health_detail() -> dict[str, Any]:
    components = {
        "model": _check_model(),
        "redis": _check_redis(),
        "kafka": _check_kafka(),
        "firebase": _check_firebase(),
    }
    # 하나라도 error면 전체 degraded
    statuses = {v["status"] for v in components.values()}
    overall = "ok" if statuses <= {"ok", "disabled", "stopped"} else "degraded"
    return {"status": overall, "components": components}
