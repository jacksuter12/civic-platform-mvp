"""
Thread routes — the core deliberation surface.

Session 3 changes:
- GET /threads requires community_slug; filters to that community only.
- POST /threads requires registered membership in the specified community.
- GET /{thread_id} checks community.is_public for unauthenticated access;
  returns community_slug in the response.
- PATCH /{thread_id}/advance enforces community-scoped facilitator tier
  (replacing global FacilitatorUser).
- All write actions pass community_id to log_event().
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, OptionalUser, check_community_membership
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.community import Community
from app.models.domain import Domain
from app.models.post import Post
from app.models.proposal import Proposal
from app.models.signal import Signal, SignalTargetType, SignalType
from app.models.thread import Thread, ThreadStatus
from app.models.user import UserTier
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
        .where(
            Signal.target_type == SignalTargetType.THREAD,
            Signal.target_id == thread_id,
        )
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
    user: OptionalUser,
    community_slug: Annotated[str, Query()],
    domain_slug: Annotated[str | None, Query()] = None,
    status_filter: Annotated[ThreadStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ThreadSummary]:
    # Resolve community
    comm_result = await db.execute(
        select(Community).where(Community.slug == community_slug, Community.is_active == True)
    )
    community = comm_result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found.")

    # Private communities: 404 to unauthenticated callers
    if not community.is_public and user is None:
        raise HTTPException(status_code=404, detail="Community not found.")

    q = (
        select(Thread)
        .options(selectinload(Thread.domain))
        .where(Thread.community_id == community.id)
    )
    if domain_slug:
        domain_result = await db.execute(
            select(Domain).where(
                Domain.slug == domain_slug,
                Domain.community_id == community.id,
            )
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
                community_id=t.community_id,
                community_slug=community.slug,
                domain_id=t.domain_id,
                domain_name=t.domain.name,
                domain_slug=t.domain.slug,
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
    user: CurrentUser,
    db: DB,
) -> ThreadSummary:
    # Validate community exists and is active
    comm_result = await db.execute(
        select(Community).where(Community.id == payload.community_id, Community.is_active == True)
    )
    community = comm_result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found or inactive.")

    # Community membership check — registered tier required
    await check_community_membership(user, community.id, UserTier.REGISTERED, db)

    # Validate domain exists, is active, and belongs to this community
    domain_result = await db.execute(
        select(Domain).where(
            Domain.id == payload.domain_id,
            Domain.is_active == True,
            Domain.community_id == community.id,
        )
    )
    domain = domain_result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found or does not belong to community.")

    thread = Thread(
        community_id=community.id,
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
        community_id=community.id,
    )

    return ThreadSummary(
        id=thread.id,
        community_id=thread.community_id,
        community_slug=community.slug,
        domain_id=thread.domain_id,
        domain_name=domain.name,
        domain_slug=domain.slug,
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
        select(Thread)
        .options(selectinload(Thread.domain))
        .where(Thread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    # Community visibility check for unauthenticated users
    community_slug: str | None = None
    if thread.community_id is not None:
        comm_result = await db.execute(
            select(Community).where(Community.id == thread.community_id)
        )
        community = comm_result.scalar_one_or_none()
        if community:
            community_slug = community.slug
            if not community.is_public and user is None:
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
                Signal.user_id == user.id,
                Signal.target_type == SignalTargetType.THREAD,
                Signal.target_id == thread.id,
            )
        )
        sig = sig_result.scalar_one_or_none()
        my_signal = sig.signal_type if sig else None

    from app.schemas.user import UserPublic
    creator = UserPublic.model_validate(thread.created_by)

    return ThreadDetail(
        id=thread.id,
        community_id=thread.community_id,
        community_slug=community_slug,
        domain_id=thread.domain_id,
        domain_name=thread.domain.name,
        domain_slug=thread.domain.slug,
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
    user: CurrentUser,
    db: DB,
) -> ThreadSummary:
    """
    Advance a thread to the next deliberation phase.
    Requires facilitator-tier membership in the thread's community.
    """
    result = await db.execute(
        select(Thread).options(selectinload(Thread.domain)).where(Thread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    if thread.community_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Thread has no community; cannot advance phase.",
        )

    # Community-scoped facilitator check
    await check_community_membership(user, thread.community_id, UserTier.FACILITATOR, db)

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
        actor_id=user.id,
        community_id=thread.community_id,
    )

    sc = await _signal_counts(db, thread.id)
    pc = await _post_count(db, thread.id)
    rc = await _proposal_count(db, thread.id)

    # Fetch community slug for response
    comm_slug_result = await db.execute(
        select(Community.slug).where(Community.id == thread.community_id)
    )
    community_slug = comm_slug_result.scalar_one_or_none()

    return ThreadSummary(
        id=thread.id,
        community_id=thread.community_id,
        community_slug=community_slug,
        domain_id=thread.domain_id,
        domain_name=thread.domain.name,
        domain_slug=thread.domain.slug,
        title=thread.title,
        status=thread.status,
        signal_counts=sc,
        post_count=pc,
        proposal_count=rc,
        phase_ends_at=thread.phase_ends_at,
        created_at=thread.created_at,
    )
