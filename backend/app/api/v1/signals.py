"""
Signal routes — structured participant sentiment.

Signals are polymorphic: one signal per user per target (thread, post,
proposal, proposal_comment, amendment). Updating a signal replaces the prior
one (recorded as SIGNAL_UPDATED). Signals are aggregated and shown
anonymously; individual attribution is not exposed.

Session 3: community_id is resolved from the target object and checked
for registered-tier membership before write operations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, OptionalUser, check_community_membership
from app.core.audit import log_event
from app.models.amendment import Amendment
from app.models.audit import AuditEventType
from app.models.post import Post
from app.models.proposal import Proposal
from app.models.proposal_comment import ProposalComment
from app.models.signal import Signal, SignalTargetType, SignalType
from app.models.thread import Thread
from app.models.user import UserTier

router = APIRouter()


class SignalUpsert(BaseModel):
    target_type: SignalTargetType
    target_id: uuid.UUID
    signal_type: SignalType
    note: str | None = None


class SignalOut(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    target_type: SignalTargetType
    target_id: uuid.UUID
    signal_type: SignalType
    note: str | None


class SignalCountsOut(BaseModel):
    """Signal counts for one target, plus the caller's current signal."""
    support: int = 0
    concern: int = 0
    need_info: int = 0
    block: int = 0
    total: int = 0
    my_signal: str | None = None


async def _resolve_community_id(
    target_type: SignalTargetType,
    target_id: uuid.UUID,
    db,
) -> uuid.UUID | None:
    """Resolve community_id from any signal target type via the parent chain."""
    if target_type == SignalTargetType.THREAD:
        r = await db.execute(select(Thread.community_id).where(Thread.id == target_id))
        return r.scalar_one_or_none()

    if target_type == SignalTargetType.POST:
        r = await db.execute(select(Post.thread_id).where(Post.id == target_id))
        thread_id = r.scalar_one_or_none()
        if thread_id is None:
            return None
        r2 = await db.execute(select(Thread.community_id).where(Thread.id == thread_id))
        return r2.scalar_one_or_none()

    if target_type == SignalTargetType.PROPOSAL:
        r = await db.execute(select(Proposal.thread_id).where(Proposal.id == target_id))
        thread_id = r.scalar_one_or_none()
        if thread_id is None:
            return None
        r2 = await db.execute(select(Thread.community_id).where(Thread.id == thread_id))
        return r2.scalar_one_or_none()

    if target_type == SignalTargetType.PROPOSAL_COMMENT:
        r = await db.execute(
            select(ProposalComment.proposal_id).where(ProposalComment.id == target_id)
        )
        proposal_id = r.scalar_one_or_none()
        if proposal_id is None:
            return None
        r2 = await db.execute(select(Proposal.thread_id).where(Proposal.id == proposal_id))
        thread_id = r2.scalar_one_or_none()
        if thread_id is None:
            return None
        r3 = await db.execute(select(Thread.community_id).where(Thread.id == thread_id))
        return r3.scalar_one_or_none()

    if target_type == SignalTargetType.AMENDMENT:
        r = await db.execute(select(Amendment.proposal_id).where(Amendment.id == target_id))
        proposal_id = r.scalar_one_or_none()
        if proposal_id is None:
            return None
        r2 = await db.execute(select(Proposal.thread_id).where(Proposal.id == proposal_id))
        thread_id = r2.scalar_one_or_none()
        if thread_id is None:
            return None
        r3 = await db.execute(select(Thread.community_id).where(Thread.id == thread_id))
        return r3.scalar_one_or_none()

    return None


@router.get("/batch", response_model=dict[str, SignalCountsOut])
async def batch_signal_counts(
    target_type: Annotated[SignalTargetType, Query()],
    target_ids: Annotated[str, Query(description="Comma-separated UUIDs")],
    db: DB,
    user: OptionalUser,
) -> dict[str, SignalCountsOut]:
    """
    Return signal counts (and the caller's signal) for multiple targets of one type.
    No per-item round-trips needed — call once per content type after page render.

    Example: GET /signals/batch?target_type=post&target_ids=uuid1,uuid2,uuid3
    """
    try:
        ids = [uuid.UUID(i.strip()) for i in target_ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID in target_ids.")

    if not ids:
        return {}

    # Aggregate counts per (target_id, signal_type)
    rows = await db.execute(
        select(Signal.target_id, Signal.signal_type, func.count(Signal.id).label("cnt"))
        .where(Signal.target_type == target_type, Signal.target_id.in_(ids))
        .group_by(Signal.target_id, Signal.signal_type)
    )

    result: dict[str, SignalCountsOut] = {
        str(i): SignalCountsOut() for i in ids
    }
    for target_id, signal_type, cnt in rows:
        key = str(target_id)
        bucket = result[key]
        setattr(bucket, signal_type.value, cnt)
        bucket.total += cnt

    # Resolve caller's own signals if authenticated
    if user:
        my_rows = await db.execute(
            select(Signal.target_id, Signal.signal_type)
            .where(
                Signal.target_type == target_type,
                Signal.target_id.in_(ids),
                Signal.user_id == user.id,
            )
        )
        for target_id, signal_type in my_rows:
            key = str(target_id)
            if key in result:
                result[key].my_signal = signal_type.value

    return result


@router.post("", response_model=SignalOut, status_code=status.HTTP_200_OK)
async def upsert_signal(
    payload: SignalUpsert, user: CurrentUser, db: DB
) -> Signal:
    """
    Cast or update a signal on any supported target type.
    Requires registered-tier membership in the target's community.
    """
    community_id = await _resolve_community_id(payload.target_type, payload.target_id, db)
    if community_id is not None:
        await check_community_membership(user, community_id, UserTier.REGISTERED, db)

    existing_result = await db.execute(
        select(Signal).where(
            Signal.user_id == user.id,
            Signal.target_type == payload.target_type,
            Signal.target_id == payload.target_id,
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
                "target_type": payload.target_type.value,
                "target_id": str(payload.target_id),
            },
            actor_id=user.id,
            community_id=community_id,
        )
        return existing
    else:
        signal = Signal(
            user_id=user.id,
            target_type=payload.target_type,
            target_id=payload.target_id,
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
                "target_type": payload.target_type.value,
                "target_id": str(payload.target_id),
            },
            actor_id=user.id,
            community_id=community_id,
        )
        return signal


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def remove_signal(
    target_type: Annotated[SignalTargetType, Query()],
    target_id: Annotated[uuid.UUID, Query()],
    user: CurrentUser,
    db: DB,
) -> None:
    """
    Remove the current user's signal from a target (toggle-off).
    Requires registered-tier membership in the target's community.
    """
    community_id = await _resolve_community_id(target_type, target_id, db)
    if community_id is not None:
        await check_community_membership(user, community_id, UserTier.REGISTERED, db)

    result = await db.execute(
        select(Signal).where(
            Signal.user_id == user.id,
            Signal.target_type == target_type,
            Signal.target_id == target_id,
        )
    )
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found.")

    old_type = signal.signal_type
    await db.delete(signal)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.SIGNAL_UPDATED,
        target_type="signal",
        target_id=signal.id,
        payload={
            "from": old_type.value,
            "to": None,
            "action": "removed",
            "target_type": target_type.value,
            "target_id": str(target_id),
        },
        actor_id=user.id,
        community_id=community_id,
    )
