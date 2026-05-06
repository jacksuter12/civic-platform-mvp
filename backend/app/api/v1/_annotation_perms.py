"""
Permission and phase-gate logic for annotation actions.

Separate file because these checks are called from multiple routes
(create, reply, react, resolve, unresolve, soft-delete) and the logic
should exist in exactly one place.
"""
import uuid as _uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.annotation import Annotation
from app.models.community_membership import CommunityMembership
from app.models.proposal import Proposal
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


TIER_RANK = {
    UserTier.REGISTERED: 1,
    UserTier.PARTICIPANT: 2,
    UserTier.FACILITATOR: 3,
    UserTier.ADMIN: 4,
}


async def _get_community_context_for_proposal(
    db: AsyncSession, proposal_id
) -> tuple[Proposal, Thread]:
    if isinstance(proposal_id, str):
        proposal_id = _uuid.UUID(proposal_id)
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(500, "Thread not found for proposal")
    return proposal, thread


async def _get_membership(
    db: AsyncSession, user_id, community_id
) -> CommunityMembership | None:
    result = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.user_id == user_id,
            CommunityMembership.community_id == community_id,
        )
    )
    return result.scalar_one_or_none()


async def require_can_annotate(
    db: AsyncSession, user: User, target_type: str, target_id
) -> tuple[Proposal | None, Thread | None]:
    """
    Returns (proposal, thread) when target_type='proposal' so callers can
    use them for audit logging without a redundant DB query. Returns
    (None, None) for target_type='wiki'. Raises HTTPException on denial.
    """
    if target_type == "wiki":
        if not user.has_annotator_capability():
            raise HTTPException(403, "Annotator capability required for wiki annotations")
        return None, None

    if target_type == "proposal":
        proposal, thread = await _get_community_context_for_proposal(db, target_id)
        if thread.status != ThreadStatus.PROPOSING:
            raise HTTPException(
                403,
                "Annotations on proposals can only be created or modified "
                "during the PROPOSING phase",
            )
        membership = await _get_membership(db, user.id, thread.community_id)
        if not membership or TIER_RANK[membership.tier] < TIER_RANK[UserTier.REGISTERED]:
            raise HTTPException(403, "Community membership required")
        return proposal, thread

    raise HTTPException(400, f"Annotations on target_type={target_type!r} are not supported")


async def require_can_resolve(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal, Thread]:
    if annotation.target_type != "proposal":
        raise HTTPException(400, "Only proposal annotations can be resolved")

    proposal, thread = await _get_community_context_for_proposal(db, annotation.target_id)

    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(403, "Resolve/unresolve is only allowed during PROPOSING")

    if annotation.author_id == user.id:
        return proposal, thread
    if proposal.created_by_id == user.id:
        return proposal, thread
    membership = await _get_membership(db, user.id, thread.community_id)
    if membership and TIER_RANK[membership.tier] >= TIER_RANK[UserTier.FACILITATOR]:
        return proposal, thread

    raise HTTPException(
        403,
        "Only the annotation author, proposal author, or community "
        "facilitators can resolve this annotation",
    )


async def require_can_moderate(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal | None, Thread | None]:
    if annotation.target_type == "wiki":
        if user.platform_role != "platform_admin" and not user.is_annotator:
            raise HTTPException(403, "Cannot moderate wiki annotations")
        return None, None

    if annotation.target_type == "proposal":
        proposal, thread = await _get_community_context_for_proposal(db, annotation.target_id)
        membership = await _get_membership(db, user.id, thread.community_id)
        if not membership or TIER_RANK[membership.tier] < TIER_RANK[UserTier.FACILITATOR]:
            raise HTTPException(
                403, "Only community facilitators can moderate proposal annotations"
            )
        return proposal, thread

    raise HTTPException(400, f"Cannot moderate annotations of type {annotation.target_type!r}")


async def require_can_feature(
    db: AsyncSession, user: User, annotation: Annotation
) -> tuple[Proposal, Thread]:
    """Only facilitators in the annotation's community can feature; proposal-type only."""
    if annotation.target_type != "proposal":
        raise HTTPException(400, "Only proposal annotations can be featured")
    proposal, thread = await _get_community_context_for_proposal(db, annotation.target_id)
    membership = await _get_membership(db, user.id, thread.community_id)
    if not membership or TIER_RANK[membership.tier] < TIER_RANK[UserTier.FACILITATOR]:
        raise HTTPException(403, "Only community facilitators can feature annotations")
    return proposal, thread


# ---------------------------------------------------------------------------
# Non-raising check variants — return bool instead of raising
# ---------------------------------------------------------------------------


async def check_can_resolve(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    if not user:
        return False
    try:
        await require_can_resolve(db, user, annotation)
        return True
    except HTTPException:
        return False


async def check_can_moderate(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    if not user:
        return False
    try:
        await require_can_moderate(db, user, annotation)
        return True
    except HTTPException:
        return False


async def check_can_feature(
    db: AsyncSession, user: User | None, annotation: Annotation
) -> bool:
    if not user:
        return False
    try:
        await require_can_feature(db, user, annotation)
        return True
    except HTTPException:
        return False


# ---------------------------------------------------------------------------
# Proposal edit permission helpers
# ---------------------------------------------------------------------------


async def require_can_edit_proposal(
    db: AsyncSession, user: User, proposal_id
) -> tuple[Proposal, Thread]:
    """Author-only, PROPOSING phase only. Raises HTTPException on denial."""
    if isinstance(proposal_id, str):
        proposal_id = _uuid.UUID(proposal_id)
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal.created_by_id != user.id:
        raise HTTPException(403, "Only the proposal author can edit their proposal")
    result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(500, "Thread not found for proposal")
    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            403,
            f"Proposals can only be edited during the PROPOSING phase. "
            f"This thread is in {thread.status.value}.",
        )
    return proposal, thread


async def check_can_edit_proposal(
    db: AsyncSession, user: "User | None", proposal: Proposal
) -> bool:
    if not user:
        return False
    try:
        await require_can_edit_proposal(db, user, proposal.id)
        return True
    except HTTPException:
        return False


async def require_can_delete_proposal(
    db: AsyncSession, user: User, proposal_id
) -> tuple[Proposal, Thread]:
    """Author-only, PROPOSING phase only, not already deleted. Raises HTTPException on denial."""
    if isinstance(proposal_id, str):
        proposal_id = _uuid.UUID(proposal_id)
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal or proposal.deleted_at is not None:
        raise HTTPException(404, "Proposal not found")
    if proposal.created_by_id != user.id:
        raise HTTPException(403, "Only the proposal author can delete their proposal")
    result = await db.execute(select(Thread).where(Thread.id == proposal.thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(500, "Thread not found for proposal")
    if thread.status != ThreadStatus.PROPOSING:
        raise HTTPException(
            403,
            f"Proposals can only be deleted during the PROPOSING phase. "
            f"This thread is in {thread.status.value}.",
        )
    return proposal, thread


async def check_can_delete_proposal(
    db: AsyncSession, user: "User | None", proposal: Proposal
) -> bool:
    if not user:
        return False
    try:
        await require_can_delete_proposal(db, user, proposal.id)
        return True
    except HTTPException:
        return False
