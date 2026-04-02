"""
Audit route — the primary public transparency surface.

This is read-only. No authentication required.
All significant platform actions are queryable here.

Design intent: civil society observers, researchers, and participants
can independently verify that platform decisions match the audit trail.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select, func

from app.api.deps import DB
from app.models.audit import AuditEventType, AuditLog
from app.schemas.audit import AuditLogEntry, AuditLogPage

router = APIRouter()


@router.get("", response_model=AuditLogPage)
async def list_audit_events(
    db: DB,
    event_type: Annotated[AuditEventType | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    """
    Public read endpoint for the transparency log.

    Supports filtering by event_type, target_type, target_id, actor_id.
    Results ordered newest-first.

    Use this to answer questions like:
    - "What happened to thread X?" → filter by target_type=thread&target_id=X
    - "What did facilitator Y do?" → filter by actor_id=Y
    - "Show all allocations" → filter by event_type=allocation_decided
    """
    q = select(AuditLog)
    if event_type:
        q = q.where(AuditLog.event_type == event_type)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
    if target_id:
        q = q.where(AuditLog.target_id == target_id)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)

    count_result = await db.execute(
        select(func.count()).select_from(q.subquery())
    )
    total = count_result.scalar_one()

    q = q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    entries = [AuditLogEntry.model_validate(row) for row in result.scalars()]

    return AuditLogPage(entries=entries, total=total, limit=limit, offset=offset)
