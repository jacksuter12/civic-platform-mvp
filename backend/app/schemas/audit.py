import uuid
from datetime import datetime

from app.models.audit import AuditEventType
from app.schemas.common import CamelBase, UUIDSchema


class AuditLogEntry(UUIDSchema):
    """
    Public read-only view of audit log entries.
    actor_id is included; display_name is NOT (privacy-preserving).
    Callers can resolve actor_id to display_name separately if needed.
    """

    event_type: AuditEventType
    actor_id: uuid.UUID | None
    target_type: str
    target_id: uuid.UUID
    payload: dict
    created_at: datetime


class AuditLogPage(CamelBase):
    entries: list[AuditLogEntry]
    total: int
    limit: int
    offset: int
