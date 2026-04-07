"""
Amendment routes — proposed changes to a specific proposal's text.

Key rules enforced here:
- Only PROPOSING phase allows amendment submission.
- A participant cannot amend their own proposal (prevents self-acceptance gaming).
- Only the proposal's author may accept or reject an amendment.
- Acceptance is a signal of intent only — it does NOT rewrite the proposal text.
- Every write action is audit logged.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ParticipantUser
from app.core.audit import log_event
from app.models.amendment import Amendment, AmendmentStatus
from app.models.audit import AuditEventType
from app.models.proposal import Proposal
from app.models.thread import Thread, ThreadStatus
from app.schemas.amendment import AmendmentCreate, AmendmentRead, AmendmentReview
from app.schemas.user import UserPublic

router = APIRouter()


async def _get_proposal_and_thread(
    proposal_id: uuid.UUID, db: DB
) -> tuple[Proposal, Thread]:
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    thread_result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = thread_result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    return proposal, thread


@router.post(
    "/{proposal_id}/amendments",
    response_model=AmendmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_amendment(
    proposal_id: uuid.UUID,
    payload: AmendmentCreate,
    user: ParticipantUser,
    db: DB,
) -> AmendmentRead:
    """
    Submit an amendment to a proposal. PARTICIPANT tier required.
    - Only allowed while the parent thread is in PROPOSING phase.
    - Cannot amend your own proposal.
    """
    proposal, thread = await _get_proposal_and_thread(proposal_id, db)

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Amendments can only be submitted during 'proposing' phase. "
                f"Current phase: '{thread.status.value}'."
            ),
        )

    if proposal.created_by_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot amend your own proposal. Ask another participant to submit the amendment.",
        )

    amendment = Amendment(
        proposal_id=proposal_id,
        author_id=user.id,
        title=payload.title,
        original_text=payload.original_text,
        proposed_text=payload.proposed_text,
        rationale=payload.rationale,
    )
    db.add(amendment)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.AMENDMENT_SUBMITTED,
        target_type="amendment",
        target_id=amendment.id,
        payload={
            "proposal_id": str(proposal_id),
            "thread_id": str(thread.id),
            "title": payload.title,
        },
        actor_id=user.id,
    )

    await db.refresh(amendment)
    return AmendmentRead(
        id=amendment.id,
        proposal_id=amendment.proposal_id,
        author=UserPublic.model_validate(user),
        title=amendment.title,
        original_text=amendment.original_text,
        proposed_text=amendment.proposed_text,
        rationale=amendment.rationale,
        status=amendment.status,
        reviewed_at=amendment.reviewed_at,
        created_at=amendment.created_at,
        updated_at=amendment.updated_at,
    )


@router.get(
    "/{proposal_id}/amendments",
    response_model=list[AmendmentRead],
)
async def list_amendments(
    proposal_id: uuid.UUID,
    db: DB,
) -> list[AmendmentRead]:
    """
    Return all amendments on a proposal, ordered chronologically.
    Public endpoint — no auth required.
    """
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Proposal not found.")

    amendments_result = await db.execute(
        select(Amendment)
        .where(Amendment.proposal_id == proposal_id)
        .order_by(Amendment.created_at)
    )
    amendments = list(amendments_result.scalars())

    out = []
    for a in amendments:
        await db.refresh(a, ["author"])
        out.append(
            AmendmentRead(
                id=a.id,
                proposal_id=a.proposal_id,
                author=UserPublic.model_validate(a.author),
                title=a.title,
                original_text=a.original_text,
                proposed_text=a.proposed_text,
                rationale=a.rationale,
                status=a.status,
                reviewed_at=a.reviewed_at,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )
    return out


@router.patch(
    "/{proposal_id}/amendments/{amendment_id}/review",
    response_model=AmendmentRead,
)
async def review_amendment(
    proposal_id: uuid.UUID,
    amendment_id: uuid.UUID,
    payload: AmendmentReview,
    user: CurrentUser,
    db: DB,
) -> AmendmentRead:
    """
    Accept or reject an amendment. Only the proposal's author may call this.

    Acceptance records intent only — the proposal text is NOT automatically
    updated. The proposer must manually revise their proposal text.
    """
    proposal, _ = await _get_proposal_and_thread(proposal_id, db)

    if proposal.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the proposal's author may accept or reject amendments.",
        )

    result = await db.execute(
        select(Amendment).where(
            Amendment.id == amendment_id,
            Amendment.proposal_id == proposal_id,
        )
    )
    amendment = result.scalar_one_or_none()
    if not amendment:
        raise HTTPException(status_code=404, detail="Amendment not found.")

    if amendment.status != AmendmentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Amendment has already been reviewed (status: '{amendment.status.value}').",
        )

    amendment.status = payload.status
    amendment.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    event_type = (
        AuditEventType.AMENDMENT_ACCEPTED
        if payload.status == AmendmentStatus.ACCEPTED
        else AuditEventType.AMENDMENT_REJECTED
    )
    await log_event(
        db,
        event_type=event_type,
        target_type="amendment",
        target_id=amendment.id,
        payload={
            "proposal_id": str(proposal_id),
            "status": payload.status.value,
            "reviewer_note": payload.reviewer_note,
        },
        actor_id=user.id,
    )

    await db.refresh(amendment, ["author"])
    return AmendmentRead(
        id=amendment.id,
        proposal_id=amendment.proposal_id,
        author=UserPublic.model_validate(amendment.author),
        title=amendment.title,
        original_text=amendment.original_text,
        proposed_text=amendment.proposed_text,
        rationale=amendment.rationale,
        status=amendment.status,
        reviewed_at=amendment.reviewed_at,
        created_at=amendment.created_at,
        updated_at=amendment.updated_at,
    )
