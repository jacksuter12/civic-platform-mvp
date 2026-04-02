"""
Proposal routes — the bridge between deliberation and allocation.

Phase gate: proposals may only be submitted when thread.status == PROPOSING.
Voting on proposals only permitted when thread.status == VOTING.

Vote tallies are computed on read in MVP (no caching). Before marking a
proposal PASSED or REJECTED, a facilitator must advance the thread to CLOSED;
the system records a vote_summary snapshot at that time.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from typing import Annotated

from app.api.deps import DB, FacilitatorUser, ParticipantUser, RegisteredUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.proposal import Proposal, ProposalStatus
from app.models.thread import Thread, ThreadStatus
from app.models.vote import Vote, VoteChoice
from app.schemas.proposal import (
    ProposalCreate,
    ProposalDetail,
    ProposalStatusUpdate,
    ProposalSummary,
    VoteSummary,
)
from app.schemas.user import UserPublic

router = APIRouter()


async def _vote_summary(db: DB, proposal_id: uuid.UUID) -> VoteSummary:
    rows = await db.execute(
        select(Vote.choice, func.count(Vote.id))
        .where(Vote.proposal_id == proposal_id)
        .group_by(Vote.choice)
    )
    counts = {row[0]: row[1] for row in rows}
    yes = counts.get(VoteChoice.YES, 0)
    no = counts.get(VoteChoice.NO, 0)
    abstain = counts.get(VoteChoice.ABSTAIN, 0)
    return VoteSummary(yes=yes, no=no, abstain=abstain, total=yes + no + abstain)


@router.get("/thread/{thread_id}", response_model=list[ProposalSummary])
async def list_proposals(
    thread_id: uuid.UUID,
    db: DB,
    user: RegisteredUser | None = None,
) -> list[ProposalSummary]:
    result = await db.execute(
        select(Proposal)
        .where(Proposal.thread_id == thread_id)
        .order_by(Proposal.created_at)
    )
    proposals = list(result.scalars())

    summaries = []
    for p in proposals:
        vs = await _vote_summary(db, p.id)
        my_vote = None
        if user:
            vr = await db.execute(
                select(Vote).where(
                    Vote.proposal_id == p.id, Vote.voter_id == user.id
                )
            )
            v = vr.scalar_one_or_none()
            my_vote = v.choice if v else None
        summaries.append(
            ProposalSummary(
                id=p.id,
                thread_id=p.thread_id,
                title=p.title,
                status=p.status,
                requested_amount=p.requested_amount,
                vote_summary=vs,
                my_vote=my_vote,
                created_at=p.created_at,
            )
        )
    return summaries


@router.post(
    "", response_model=ProposalSummary, status_code=status.HTTP_201_CREATED
)
async def create_proposal(
    payload: ProposalCreate,
    thread_id: uuid.UUID,
    user: ParticipantUser,
    db: DB,
) -> ProposalSummary:
    thread_result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = thread_result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Proposals can only be submitted when thread is in 'proposing' phase. Current: '{thread.status.value}'.",
        )

    proposal = Proposal(
        thread_id=thread_id,
        created_by_id=user.id,
        title=payload.title,
        description=payload.description,
        requested_amount=payload.requested_amount,
        status=ProposalStatus.SUBMITTED,
    )
    db.add(proposal)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.PROPOSAL_CREATED,
        target_type="proposal",
        target_id=proposal.id,
        payload={"title": proposal.title, "thread_id": str(thread_id)},
        actor_id=user.id,
    )

    return ProposalSummary(
        id=proposal.id,
        thread_id=proposal.thread_id,
        title=proposal.title,
        status=proposal.status,
        requested_amount=proposal.requested_amount,
        vote_summary=VoteSummary(),
        created_at=proposal.created_at,
    )


@router.patch("/{proposal_id}/status", response_model=ProposalSummary)
async def update_proposal_status(
    proposal_id: uuid.UUID,
    payload: ProposalStatusUpdate,
    facilitator: FacilitatorUser,
    db: DB,
) -> ProposalSummary:
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    old_status = proposal.status
    proposal.status = payload.new_status

    vs = await _vote_summary(db, proposal.id)

    await log_event(
        db,
        event_type=AuditEventType.PROPOSAL_STATUS_CHANGED,
        target_type="proposal",
        target_id=proposal.id,
        payload={
            "from_status": old_status.value,
            "to_status": payload.new_status.value,
            "reason": payload.reason,
            "vote_summary": vs.model_dump(),
        },
        actor_id=facilitator.id,
    )

    return ProposalSummary(
        id=proposal.id,
        thread_id=proposal.thread_id,
        title=proposal.title,
        status=proposal.status,
        requested_amount=proposal.requested_amount,
        vote_summary=vs,
        created_at=proposal.created_at,
    )
