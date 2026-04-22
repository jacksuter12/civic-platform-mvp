"""
Audit log writer. All significant actions pass through here.

Design contract:
- log_event() only inserts — never updates or deletes.
- Callers must pass the active session; the audit entry is part of
  the same transaction as the action it records.
- If the outer transaction rolls back, the audit entry rolls back too.
  This prevents phantom audit entries for failed operations.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEventType, AuditLog

log = structlog.get_logger()


async def log_event(
    db: AsyncSession,
    event_type: AuditEventType,
    target_type: str,
    target_id: uuid.UUID,
    payload: dict,
    actor_id: uuid.UUID | None = None,
    community_id: uuid.UUID | None = None,
) -> AuditLog:
    """
    Insert an audit log entry in the current transaction.

    Args:
        db: Active async session (caller owns commit/rollback).
        event_type: What happened.
        target_type: Model name of the affected object.
        target_id: PK of the affected object.
        payload: Snapshot of relevant data at the time of the event.
        actor_id: Who did it (None for system events).
        community_id: The community this event belongs to, or None for
            platform-level events (user registration, annotator grants, etc.).
            All existing call sites omit this argument and implicitly pass None.
    """
    entry = AuditLog(
        event_type=event_type,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        community_id=community_id,
    )
    db.add(entry)
    await db.flush()  # assign PK; caller commits

    log.info(
        "audit_event",
        event_type=event_type.value,
        target_type=target_type,
        target_id=str(target_id),
        actor_id=str(actor_id) if actor_id else None,
        community_id=str(community_id) if community_id else None,
    )

    return entry
