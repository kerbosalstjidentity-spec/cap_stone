"""Step-up Auth 대기 트랜잭션 store — Redis hash backed, 인메모리 폴백.

W2-#2: routes_fraud._stepup_store dict + _stepup_lock 을 외부화.
멀티 인스턴스 환경에서 사용자가 다른 노드로 step-up 결과를 보내도
같은 tx 상태를 조회·갱신할 수 있어야 한다.

키 전략:
  stepup:{tx_id}  → Redis Hash {score, amount, reason_code, pre_action,
                                 status, resolved_action}
  TTL: 환경변수 STEPUP_TTL_SEC (기본 30분, 사용자 응답 대기 한계)

Redis 미가용 시 프로세스 메모리 dict로 폴백 (싱글 인스턴스 한정).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

try:
    import redis as redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
STEPUP_TTL_SEC = int(os.getenv("STEPUP_TTL_SEC", "1800"))
_KEY_PREFIX = "stepup:"

# 인메모리 폴백
_local_store: dict[str, dict[str, Any]] = {}
_local_lock = threading.Lock()

_redis_client = None


def _get_redis():
    """Sync Redis 클라이언트 lazy init. 실패 시 None (폴백 모드)."""
    global _redis_client
    if not _HAS_REDIS or not REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
        logger.info("[stepup-store] Redis 연결 성공: %s", REDIS_URL)
    except Exception as e:
        logger.warning("[stepup-store] Redis 연결 실패, in-memory 폴백: %s", e)
        _redis_client = None
    return _redis_client


def _key(tx_id: str) -> str:
    return f"{_KEY_PREFIX}{tx_id}"


def set_pending(tx_id: str, entry: dict[str, Any], ttl_s: int = STEPUP_TTL_SEC) -> None:
    """step-up 대기 항목 등록. status='pending'으로 시작."""
    r = _get_redis()
    if r is not None:
        try:
            mapping = {k: ("" if v is None else str(v)) for k, v in entry.items()}
            pipe = r.pipeline()
            pipe.hset(_key(tx_id), mapping=mapping)
            pipe.expire(_key(tx_id), ttl_s)
            pipe.execute()
            return
        except Exception as e:
            logger.warning("[stepup-store] Redis hset 실패, 폴백: %s", e)
    with _local_lock:
        _local_store[tx_id] = dict(entry)


def get(tx_id: str) -> dict[str, Any] | None:
    """tx_id 로 entry 조회. 없으면 None."""
    r = _get_redis()
    if r is not None:
        try:
            data = r.hgetall(_key(tx_id))
            if data:
                # Redis는 모두 string — 숫자 필드 복원
                return _coerce_types(data)
        except Exception as e:
            logger.warning("[stepup-store] Redis hgetall 실패, 폴백 확인: %s", e)
    with _local_lock:
        entry = _local_store.get(tx_id)
        return dict(entry) if entry else None


def update_status(tx_id: str, status: str, resolved_action: str | None = None) -> bool:
    """status (+ resolved_action) 업데이트. tx 없으면 False."""
    r = _get_redis()
    if r is not None:
        try:
            if not r.exists(_key(tx_id)):
                # 폴백 매장도 확인
                pass
            else:
                mapping = {"status": status}
                if resolved_action is not None:
                    mapping["resolved_action"] = resolved_action
                r.hset(_key(tx_id), mapping=mapping)
                return True
        except Exception as e:
            logger.warning("[stepup-store] Redis update 실패, 폴백: %s", e)
    with _local_lock:
        entry = _local_store.get(tx_id)
        if entry is None:
            return False
        entry["status"] = status
        if resolved_action is not None:
            entry["resolved_action"] = resolved_action
        return True


def _coerce_types(data: dict[str, str]) -> dict[str, Any]:
    """Redis hash에서 가져온 string 값을 원래 타입으로 best-effort 복원."""
    out: dict[str, Any] = dict(data)
    for k in ("score", "amount"):
        if k in out and out[k] not in ("", None):
            try:
                out[k] = float(out[k])
            except (TypeError, ValueError):
                pass
    return out


__all__ = ["STEPUP_TTL_SEC", "get", "set_pending", "update_status"]
