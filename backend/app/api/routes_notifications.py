"""실시간 알림 API — WebSocket + REST."""

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.notification import NotificationList, NotificationResponse, UnreadCount
from app.services.notification_service import (
    notification_manager,
    get_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_read,
)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


# ── WebSocket 엔드포인트 ─────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """실시간 알림 수신 WebSocket.

    연결: ws://host/v1/notifications/ws?token={jwt_access_token}
    """
    # JWT에서 user_id 추출
    from app.auth.jwt import decode_token
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await notification_manager.connect(user_id, websocket)
    try:
        while True:
            # 클라이언트 → 서버 메시지 (ping/pong 유지용)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        notification_manager.disconnect(user_id, websocket)
    except Exception:
        notification_manager.disconnect(user_id, websocket)


# ── REST 엔드포인트 ──────────────────────────────────────────

@router.get("/", response_model=NotificationList)
async def list_notifications(
    user_id: str = Query(...),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """알림 목록 조회 (최신순)."""
    notifications, unread, total = await get_notifications(session, user_id, limit, offset)
    return NotificationList(
        notifications=[
            NotificationResponse(
                id=n.id,
                event_type=n.event_type,
                title=n.title,
                body=n.body,
                metadata_json=n.metadata_json,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in notifications
        ],
        unread_count=unread,
        total=total,
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    user_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """안읽은 알림 수."""
    count = await get_unread_count(session, user_id)
    return UnreadCount(count=count)


@router.put("/{notification_id}/read")
async def read_notification(
    notification_id: int,
    user_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """알림 읽음 처리."""
    ok = await mark_as_read(session, notification_id, user_id)
    return {"success": ok}


@router.put("/read-all")
async def read_all_notifications(
    user_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """모든 알림 읽음 처리."""
    count = await mark_all_read(session, user_id)
    return {"marked_count": count}
