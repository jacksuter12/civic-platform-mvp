"""
Thread routes — the core deliberation surface.

Key design decisions enforced here:
- Thread creation requires PARTICIPANT tier (identity verified).
- Phase advancement requires FACILITATOR tier.
- Phase transitions follow the strict state machine in thread.VALID_TRANSITIONS.
- Every phase advance is written to the audit log with a required reason.
- Signal counts are computed from DB on read (not cached in MVP).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, FacilitatorUser, OptionalUser, ParticipantUser, RegisteredUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.domain import Domain
from app.models.post import Post
from app.models.proposal import Proposal
from app.models.signal import Signal, SignalType
from app.models.thread import Thread, ThreadStatus
from app.schemas.thread import (
    SignalCounts,
    ThreadCreate,
    ThreadDetail,
    ThreadPhaseAdvance,
    ThreadSummary,
)

router = APIRouter()


async def _signal_counts(db: DB, thread_id: uuid.UUID) -> SignalCounts:
    rows = await db.execute(
        select(Signal.signal_type, func.count(Signal.id))
        .where(Signal.thread_id == thread_id)
        .group_by(Signal.signal_type)
    )
    counts = {row[0]: row[1] for row in rows}
    return SignalCounts(
        support=counts.get(SignalType.SUPPORT, 0),
        concern=counts.get(SignalType.CONCERN, 0),
        need_info=counts.get(SignalType.NEED_INFO, 0),
        block=counts.get(SignalType.BLOCK, 0),
        total=sum(counts.values()),
    )


async def _post_count(db: DB, thread_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Post.id)).where(
            Post.thread_id == thread_id, Post.is_removed == False
        )
    )
    return result.scalar_one()


async def _proposal_count(db: DB, thread_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Proposal.id)).where(Proposal.thread_id == thread_id)
    )
    return result.scalar_one()


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    db: DB,
    domain_slug: Annotated[str | None, Query()] = None,
    status_filter: Annotated[ThreadStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ThreadSummary]:
    q = select(Thread)
    if domain_slug:
        domain_result = await db.execute(
            select(Domain).where(Domain.slug == domain_slug)
        )
        domain = domain_result.scalar_one_or_none()
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found.")
        q = q.where(Thread.domain_id == domain.id)
    if status_filter:
        q = q.where(Thread.status == status_filter)
    q = q.order_by(Thread.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    threads = list(result.scalars())

    summaries = []
    for t in threads:
        sc = await _signal_counts(db, t.id)
        pc = await _post_count(db, t.id)
        rc = await _proposal_count(db, t.id)
        summaries.append(
            ThreadSummary(
                id=t.id,
                domain_id=t.domain_id,
                title=t.title,
                status=t.status,
                signal_counts=sc,
                post_count=pc,
                proposal_count=rc,
                phase_ends_at=t.phase_ends_at,
                created_at=t.created_at,
            )
        )
    return summaries


@router.post("", response_model=ThreadSummary, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    user: ParticipantUser,
    db: DB,
) -> ThreadSummary:
    # Validate domain exists and is active
    domain_result = await db.execute(
        select(Domain).where(Domain.id == payload.domain_id, Domain.is_active == True)
    )
    if not domain_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Domain not found or inactive.")

    thread = Thread(
        domain_id=payload.domain_id,
        created_by_id=user.id,
        title=payload.title,
        prompt=payload.prompt,
        context=payload.context,
    )
    db.add(thread)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.THREAD_CREATED,
        target_type="thread",
        target_id=thread.id,
        payload={"title": thread.title, "domain_id": str(thread.domain_id)},
        actor_id=user.id,
    )

    return ThreadSummary(
        id=thread.id,
        domain_id=thread.domain_id,
        title=thread.title,
        status=thread.status,
        signal_counts=SignalCounts(),
        post_count=0,
        proposal_count=0,
        phase_ends_at=thread.phase_ends_at,
        created_at=thread.created_at,
    )


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    db: DB,
    user: OptionalUser,
) -> ThreadDetail:
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    await db.refresh(thread, ["created_by"])
    sc = await _signal_counts(db, thread.id)
    pc = await _post_count(db, thread.id)
    rc = await _proposal_count(db, thread.id)

    # Resolve caller's own signal
    my_signal = None
    if user:
        sig_result = await db.execute(
            select(Signal).where(
                Signal.thread_id == thread.id, Signal.user_id == user.id
            )
        )
        sig = sig_result.scalar_one_or_none()
        my_signal = sig.signal_type if sig else None

    from app.schemas.user import UserPublic
    creator = UserPublic.model_validate(thread.created_by)

    return ThreadDetail(
        id=thread.id,
        domain_id=thread.domain_id,
        title=thread.title,
        prompt=thread.prompt,
        context=thread.context,
        status=thread.status,
        signal_counts=sc,
        post_count=pc,
        proposal_count=rc,
        phase_ends_at=thread.phase_ends_at,
        created_at=thread.created_at,
        created_by=creator,
        my_signal=my_signal,
    )


@router.patch("/{thread_id}/advance", response_model=ThreadSummary)
async def advance_thread_phase(
    thread_id: uuid.UUID,
    payload: ThreadPhaseAdvance,
    facilitator: FacilitatorUser,
    db: DB,
) -> ThreadSummary:
    """
    Advance a thread to the next deliberation phase.
    Validates the state machine transition and writes to audit log.
    Only facilitators may call this endpoint.
    """
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    if not thread.can_advance_to(payload.target_status):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot transition from '{thread.status.value}' to "
                f"'{payload.target_status.value}'. "
                f"Valid next states: {[s.value for s in thread.status.__class__ if thread.can_advance_to(s)]}"
            ),
        )

    old_status = thread.status
    thread.status = payload.target_status
    thread.phase_ends_at = payload.phase_ends_at

    await log_event(
        db,
        event_type=AuditEventType.THREAD_PHASE_ADVANCED,
        target_type="thread",
        target_id=thread.id,
        payload={
            "from_status": old_status.value,
            "to_status": payload.target_status.value,
            "reason": payload.reason,
        },
        actor_id=facilitator.id,
    )

    sc = await _signal_counts(db, thread.id)
    pc = await _post_count(db, thread.id)
    rc = await _proposal_count(db, thread.id)

    return ThreadSummary(
        id=thread.id,
        domain_id=thread.domain_id,
        title=thread.title,
        status=thread.status,
        signal_counts=sc,
        post_count=pc,
        proposal_count=rc,
        phase_ends_at=thread.phase_ends_at,
        created_at=thread.created_at,
    )
