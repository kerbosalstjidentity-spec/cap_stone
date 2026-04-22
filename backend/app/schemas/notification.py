"""알림 시스템 스키마."""

from datetime import datetime
from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    event_type: str
    title: str
    body: str
    metadata_json: str = "{}"
    is_read: bool = False
    created_at: datetime


class NotificationList(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    total: int


class UnreadCount(BaseModel):
    count: int
