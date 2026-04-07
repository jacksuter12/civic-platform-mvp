"""
Proposal comment routes.

Phase gate: comments may only be created while thread.status == PROPOSING.
Facilitators may soft-delete comments with a required reason (audit logged).
No reactions — sentiment is captured via Signals on the proposal target.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, FacilitatorUser, ParticipantUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.proposal import Proposal
from app.models.proposal_comment import ProposalComment
from app.models.thread import Thread, ThreadStatus
from app.schemas.proposal_comment import (
    ProposalCommentCreate,
    ProposalCommentRead,
    ProposalCommentRemove,
)
from app.schemas.user import UserPublic

router = APIRouter()


async def _get_proposal_and_thread(
    proposal_id: uuid.UUID, db: DB
) -> tuple[Proposal, Thread]:
    """Load proposal + thread, 404 if not found."""
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
    "/{proposal_id}/comments",
    response_model=ProposalCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_proposal_comment(
    proposal_id: uuid.UUID,
    payload: ProposalCommentCreate,
    user: ParticipantUser,
    db: DB,
) -> ProposalCommentRead:
    """
    Submit a comment on a proposal. PARTICIPANT tier required.
    Only allowed while the parent thread is in PROPOSING phase.
    """
    proposal, thread = await _get_proposal_and_thread(proposal_id, db)

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Proposal comments can only be submitted during 'proposing' phase. "
                f"Current phase: '{thread.status.value}'."
            ),
        )

    if payload.parent_id:
        parent_result = await db.execute(
            select(ProposalComment).where(
                ProposalComment.id == payload.parent_id,
                ProposalComment.proposal_id == proposal_id,
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail="Parent comment not found on this proposal.",
            )

    comment = ProposalComment(
        proposal_id=proposal_id,
        author_id=user.id,
        parent_id=payload.parent_id,
        body=payload.body,
    )
    db.add(comment)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.PROPOSAL_COMMENT_CREATED,
        target_type="proposal_comment",
        target_id=comment.id,
        payload={
            "proposal_id": str(proposal_id),
            "thread_id": str(thread.id),
            "parent_id": str(payload.parent_id) if payload.parent_id else None,
        },
        actor_id=user.id,
    )

    await db.refresh(comment)
    return ProposalCommentRead(
        id=comment.id,
        proposal_id=comment.proposal_id,
        author=UserPublic.model_validate(user),
        parent_id=comment.parent_id,
        body=comment.body,
        is_removed=comment.is_removed,
        removal_reason=comment.removal_reason,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.get(
    "/{proposal_id}/comments",
    response_model=list[ProposalCommentRead],
)
async def list_proposal_comments(
    proposal_id: uuid.UUID,
    db: DB,
) -> list[ProposalCommentRead]:
    """
    Return all comments on a proposal, ordered chronologically.
    Public endpoint — no auth required.
    """
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Proposal not found.")

    comments_result = await db.execute(
        select(ProposalComment)
        .where(ProposalComment.proposal_id == proposal_id)
        .order_by(ProposalComment.created_at)
    )
    comments = list(comments_result.scalars())

    out = []
    for c in comments:
        await db.refresh(c, ["author"])
        out.append(
            ProposalCommentRead(
                id=c.id,
                proposal_id=c.proposal_id,
                author=UserPublic.model_validate(c.author),
                parent_id=c.parent_id,
                body=c.body,
                is_removed=c.is_removed,
                removal_reason=c.removal_reason,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )
    return out


@router.delete(
    "/{proposal_id}/comments/{comment_id}",
    response_model=ProposalCommentRead,
)
async def remove_proposal_comment(
    proposal_id: uuid.UUID,
    comment_id: uuid.UUID,
    payload: ProposalCommentRemove,
    facilitator: FacilitatorUser,
    db: DB,
) -> ProposalCommentRead:
    """
    Soft-delete a proposal comment. FACILITATOR tier required.
    Reason is required and recorded in the audit log.
    """
    result = await db.execute(
        select(ProposalComment).where(
            ProposalComment.id == comment_id,
            ProposalComment.proposal_id == proposal_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")

    if comment.is_removed:
        raise HTTPException(status_code=409, detail="Comment is already removed.")

    comment.is_removed = True
    comment.removal_reason = payload.reason
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.PROPOSAL_COMMENT_REMOVED,
        target_type="proposal_comment",
        target_id=comment.id,
        payload={
            "proposal_id": str(proposal_id),
            "reason": payload.reason,
        },
        actor_id=facilitator.id,
    )

    await db.refresh(comment, ["author"])
    return ProposalCommentRead(
        id=comment.id,
        proposal_id=comment.proposal_id,
        author=UserPublic.model_validate(comment.author),
        parent_id=comment.parent_id,
        body=comment.body,
        is_removed=comment.is_removed,
        removal_reason=comment.removal_reason,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )
