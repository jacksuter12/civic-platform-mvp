"""
Proposal routes — the bridge between deliberation and allocation.

Phase gate: proposals may only be submitted when thread.status == PROPOSING.
Voting on proposals only permitted when thread.status == VOTING.
Editing is only allowed by the proposal's author, in PROPOSING phase.

Vote tallies are computed on read in MVP (no caching). Before marking a
proposal PASSED or REJECTED, a facilitator must advance the thread to CLOSED;
the system records a vote_summary snapshot at that time.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB, FacilitatorUser, OptionalUser, ParticipantUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.proposal import Proposal, ProposalStatus
from app.models.proposal_version import ProposalVersion
from app.models.thread import Thread, ThreadStatus
from app.models.vote import Vote, VoteChoice
from app.schemas.proposal import (
    ProposalCreate,
    ProposalDetail,
    ProposalEdit,
    ProposalStatusUpdate,
    ProposalSummary,
    ProposalVersionRead,
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


async def _versions_count(db: DB, proposal_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(ProposalVersion.id)).where(
            ProposalVersion.proposal_id == proposal_id
        )
    )
    return result.scalar_one()


def _build_summary(
    p: Proposal,
    vote_summary: VoteSummary,
    versions_count: int,
    my_vote: VoteChoice | None = None,
) -> ProposalSummary:
    return ProposalSummary(
        id=p.id,
        thread_id=p.thread_id,
        title=p.title,
        description=p.description,
        status=p.status,
        requested_amount=p.requested_amount,
        vote_summary=vote_summary,
        my_vote=my_vote,
        current_version_number=p.current_version_number,
        versions_count=versions_count,
        created_at=p.created_at,
    )


@router.get("/thread/{thread_id}", response_model=list[ProposalSummary])
async def list_proposals(
    thread_id: uuid.UUID,
    db: DB,
    user: OptionalUser,
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
        vc = await _versions_count(db, p.id)
        my_vote = None
        if user:
            vr = await db.execute(
                select(Vote).where(
                    Vote.proposal_id == p.id, Vote.voter_id == user.id
                )
            )
            v = vr.scalar_one_or_none()
            my_vote = v.choice if v else None
        summaries.append(_build_summary(p, vs, vc, my_vote))
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
        current_version_number=1,
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

    return _build_summary(proposal, VoteSummary(), versions_count=0)


@router.patch("/{proposal_id}", response_model=ProposalSummary)
async def edit_proposal(
    proposal_id: uuid.UUID,
    payload: ProposalEdit,
    user: CurrentUser,
    db: DB,
) -> ProposalSummary:
    """
    Edit a proposal's title and description. Only the proposal's author may
    call this, and only while the parent thread is in PROPOSING phase.

    Before updating, a snapshot of the current state is written to
    proposal_versions, and current_version_number is incremented.
    """
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    if proposal.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the proposal's author may edit it.",
        )

    thread_result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = thread_result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Proposals can only be edited during 'proposing' phase. "
                f"Current: '{thread.status.value}'."
            ),
        )

    # Snapshot current state before overwriting
    version = ProposalVersion(
        proposal_id=proposal.id,
        author_id=user.id,
        version_number=proposal.current_version_number,
        title=proposal.title,
        description=proposal.description,
        edit_summary=payload.edit_summary,
    )
    db.add(version)

    # Apply the edit
    proposal.title = payload.title
    proposal.description = payload.description
    proposal.current_version_number += 1

    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.PROPOSAL_EDITED,
        target_type="proposal",
        target_id=proposal.id,
        payload={
            "version_archived": version.version_number,
            "new_version": proposal.current_version_number,
            "edit_summary": payload.edit_summary,
            "thread_id": str(thread.id),
        },
        actor_id=user.id,
    )

    vs = await _vote_summary(db, proposal.id)
    vc = await _versions_count(db, proposal.id)
    return _build_summary(proposal, vs, vc)


@router.get("/{proposal_id}/versions", response_model=list[ProposalVersionRead])
async def list_proposal_versions(
    proposal_id: uuid.UUID,
    db: DB,
) -> list[ProposalVersionRead]:
    """
    Return the full version history for a proposal in reverse chronological order.
    Public endpoint — no auth required.
    Each entry is a snapshot of the state that was replaced by an edit.
    """
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Proposal not found.")

    versions_result = await db.execute(
        select(ProposalVersion)
        .where(ProposalVersion.proposal_id == proposal_id)
        .order_by(ProposalVersion.version_number.desc())
    )
    versions = list(versions_result.scalars())

    out = []
    for v in versions:
        await db.refresh(v, ["author"])
        out.append(
            ProposalVersionRead(
                id=v.id,
                proposal_id=v.proposal_id,
                author=UserPublic.model_validate(v.author),
                version_number=v.version_number,
                title=v.title,
                description=v.description,
                edit_summary=v.edit_summary,
                created_at=v.created_at,
            )
        )
    return out


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
    vc = await _versions_count(db, proposal.id)

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

    return _build_summary(proposal, vs, vc)
