"""실시간 알림 서비스 — WebSocket + Redis Pub/Sub + DB 저장."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import publish, get_pubsub
from app.models.tables import Notification

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WebSocket 연결 관리자
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConnectionManager:
    """사용자별 WebSocket 연결 관리."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info("[WS] Connected: %s (total: %d)", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id] = [ws for ws in self._connections[user_id] if ws is not websocket]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("[WS] Disconnected: %s", user_id)

    async def send_to_user(self, user_id: str, data: dict) -> None:
        """특정 사용자의 모든 연결에 메시지 전송."""
        if user_id not in self._connections:
            return
        dead = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def start_redis_subscriber(self) -> None:
        """Redis Pub/Sub 구독 시작 — 알림 채널 패턴 매칭."""
        self._subscriber_task = asyncio.create_task(self._subscribe_loop())

    async def stop(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass

    async def _subscribe_loop(self) -> None:
        """Redis notify:* 패턴 구독 루프."""
        while True:
            try:
                pubsub = await get_pubsub()
                if not pubsub:
                    await asyncio.sleep(5)
                    continue

                await pubsub.psubscribe("notify:*")
                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    user_id = channel.split(":", 1)[1] if ":" in channel else ""
                    if not user_id:
                        continue
                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    await self.send_to_user(user_id, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[WS] Redis subscriber error: %s, retrying in 3s", e)
                await asyncio.sleep(3)


# 싱글턴
notification_manager = ConnectionManager()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  알림 생성 & 전송
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def create_and_push(
    session: AsyncSession,
    user_id: str,
    event_type: str,
    title: str,
    body: str = "",
    metadata: dict | None = None,
) -> Notification:
    """알림을 DB에 저장하고 Redis/WebSocket으로 실시간 전달."""
    meta_json = json.dumps(metadata or {}, default=str, ensure_ascii=False)

    notif = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        metadata_json=meta_json,
    )
    session.add(notif)
    await session.flush()

    # 실시간 전달 (fire-and-forget)
    payload = {
        "id": notif.id,
        "event_type": event_type,
        "title": title,
        "body": body,
        "metadata": metadata or {},
        "is_read": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    await publish(f"notify:{user_id}", payload)
    await notification_manager.send_to_user(user_id, payload)

    return notif


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  조회 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_notifications(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int, int]:
    """알림 목록 + 안읽은 수 + 전체 수."""
    # 목록
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    notifications = list(result.scalars().all())

    # 안읽은 수
    unread_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
    )
    unread = (await session.execute(unread_stmt)).scalar() or 0

    # 전체 수
    total_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id)
    )
    total = (await session.execute(total_stmt)).scalar() or 0

    return notifications, unread, total


async def get_unread_count(session: AsyncSession, user_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
    )
    return (await session.execute(stmt)).scalar() or 0


async def mark_as_read(session: AsyncSession, notification_id: int, user_id: str) -> bool:
    stmt = (
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
        .values(is_read=True)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def mark_all_read(session: AsyncSession, user_id: str) -> int:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
