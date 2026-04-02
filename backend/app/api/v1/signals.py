"""
Signal routes — structured participant sentiment.

Signals replace free-form reactions. One signal per user per thread.
Updating a signal replaces the prior one (recorded as SIGNAL_UPDATED).
Signals are aggregated and shown anonymously; individual attribution is not exposed.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import DB, RegisteredUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.signal import Signal, SignalType
from app.models.thread import Thread

router = APIRouter()


class SignalUpsert(BaseModel):
    thread_id: uuid.UUID
    signal_type: SignalType
    note: str | None = None


class SignalOut(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    thread_id: uuid.UUID
    signal_type: SignalType
    note: str | None


@router.post("", response_model=SignalOut, status_code=status.HTTP_200_OK)
async def upsert_signal(
    payload: SignalUpsert, user: RegisteredUser, db: DB
) -> Signal:
    """
    Cast or update a signal. Returns the current signal after upsert.
    REGISTERED tier can signal; PARTICIPANT required to post.
    """
    thread_result = await db.execute(
        select(Thread).where(Thread.id == payload.thread_id)
    )
    if not thread_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Thread not found.")

    existing_result = await db.execute(
        select(Signal).where(
            Signal.thread_id == payload.thread_id, Signal.user_id == user.id
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        old_type = existing.signal_type
        existing.signal_type = payload.signal_type
        existing.note = payload.note
        await db.flush()
        await log_event(
            db,
            event_type=AuditEventType.SIGNAL_UPDATED,
            target_type="signal",
            target_id=existing.id,
            payload={
                "from": old_type.value,
                "to": payload.signal_type.value,
                "thread_id": str(payload.thread_id),
            },
            actor_id=user.id,
        )
        return existing
    else:
        signal = Signal(
            thread_id=payload.thread_id,
            user_id=user.id,
            signal_type=payload.signal_type,
            note=payload.note,
        )
        db.add(signal)
        await db.flush()
        await log_event(
            db,
            event_type=AuditEventType.SIGNAL_CAST,
            target_type="signal",
            target_id=signal.id,
            payload={
                "signal_type": payload.signal_type.value,
                "thread_id": str(payload.thread_id),
            },
            actor_id=user.id,
        )
        return signal
