"""
Firebase FCM 푸시 발송 서비스.

환경변수:
  FIREBASE_CREDENTIALS_PATH  - serviceAccountKey.json 경로
  FIREBASE_ENABLED=true/false - 기본 false (개발 환경용)

사용 예:
  await push_service.send(fcm_token, title, body, data)
  또는 동기:
  push_service.send_sync(fcm_token, title, body)
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_FIREBASE_ENABLED = os.getenv("FIREBASE_ENABLED", "false").lower() == "true"
_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

_initialized = False


def _init_firebase() -> bool:
    global _initialized
    if _initialized:
        return True
    if not _FIREBASE_ENABLED:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate(_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("Firebase Admin SDK 초기화 완료")
        return True
    except ImportError:
        logger.warning("firebase-admin 미설치 — FCM 비활성화")
        return False
    except Exception as e:
        logger.error("Firebase 초기화 실패: %s", e)
        return False


def send_sync(
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """FCM 푸시 발송 (동기). 성공 시 True."""
    if not _init_firebase():
        logger.debug("FCM 비활성화 — push 스킵: %s", title)
        return False
    try:
        from firebase_admin import messaging
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=fcm_token,
        )
        response = messaging.send(msg)
        logger.info("FCM 발송 성공: %s", response)
        return True
    except Exception as e:
        logger.error("FCM 발송 실패: %s", e)
        return False


async def send(
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """비동기 래퍼 (run_in_executor 없이 단순 동기 호출 — FCM SDK가 동기이므로)."""
    return send_sync(fcm_token, title, body, data)


def build_step_up_payload(tx_id: str, amount: float, action_type: str) -> dict[str, Any]:
    """Step-up Auth / Block 알림용 FCM 메시지 dict 생성 (token 없이 페이로드만)."""
    amount_str = f"{int(amount):,}원"
    if action_type == "BLOCK_ALERT":
        return {
            "title": "결제 차단 알림",
            "body": f"{amount_str} 결제 시도가 차단되었습니다. 본인이 아니라면 카드를 즉시 정지하세요.",
            "data": {"tx_id": tx_id, "type": "BLOCK_ALERT"},
        }
    return {
        "title": "본인 확인 요청",
        "body": f"{amount_str} 결제 시도가 감지되었습니다. 본인이 맞으면 앱에서 승인해 주세요.",
        "data": {"tx_id": tx_id, "type": "STEP_UP_AUTH"},
    }
