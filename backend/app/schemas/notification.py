import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


class NotificationOut(UUIDSchema, TimestampSchema, CamelBase):
    notification_type: str
    actor_id: uuid.UUID | None
    target_type: str
    target_id: uuid.UUID
    community_id: uuid.UUID | None
    headline: str
    link: str | None
    is_read: bool
    read_at: datetime | None


class NotificationListOut(CamelBase):
    notifications: list[NotificationOut]
    total: int
    limit: int
    offset: int


class UnreadCountOut(BaseModel):
    count: int


class PreferencesOut(BaseModel):
    disabled: list[str]


class PreferenceUpdate(BaseModel):
    enabled: bool
