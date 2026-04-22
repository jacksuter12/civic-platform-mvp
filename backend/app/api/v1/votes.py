import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, check_community_membership
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.proposal import Proposal, ProposalStatus
from app.models.thread import Thread, ThreadStatus
from app.models.user import UserTier
from app.models.vote import Vote
from app.schemas.proposal import VoteCreate

router = APIRouter()


@router.post("/{proposal_id}", status_code=status.HTTP_201_CREATED)
async def cast_vote(
    proposal_id: uuid.UUID, payload: VoteCreate, user: CurrentUser, db: DB
) -> dict:
    """
    Cast a vote on a proposal. One vote per member per proposal. Immutable.

    Requires registered-tier membership in the proposal's community
    (lowered from participant per decision S1).
    Requires thread.status == VOTING.
    """
    proposal_result = await db.execute(
        select(Proposal).where(Proposal.id == proposal_id)
    )
    proposal = proposal_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    thread_result = await db.execute(
        select(Thread).where(Thread.id == proposal.thread_id)
    )
    thread = thread_result.scalar_one_or_none()
    if not thread or thread.status != ThreadStatus.VOTING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voting is only open when the thread is in 'voting' phase.",
        )

    # Community-scoped registered check (lowered from participant per decision S1)
    if thread.community_id is not None:
        await check_community_membership(user, thread.community_id, UserTier.REGISTERED, db)

    # Enforce one-vote-per-person
    existing = await db.execute(
        select(Vote).where(
            Vote.proposal_id == proposal_id, Vote.voter_id == user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already voted on this proposal. Votes are final.",
        )

    vote = Vote(
        proposal_id=proposal_id,
        voter_id=user.id,
        choice=payload.choice,
        rationale=payload.rationale,
    )
    db.add(vote)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.VOTE_CAST,
        target_type="vote",
        target_id=vote.id,
        payload={
            "proposal_id": str(proposal_id),
            "choice": payload.choice.value,
            # rationale omitted from audit payload to preserve deliberative privacy
        },
        actor_id=user.id,
        community_id=thread.community_id,
    )

    return {"id": str(vote.id), "choice": vote.choice.value}
