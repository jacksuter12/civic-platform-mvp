"""
Auth routes: register our User record after Supabase Auth signup.

Flow:
  1. User signs up via Supabase Auth (magic link or OAuth)
  2. Client calls POST /auth/register with the JWT and display_name
  3. We create the User record linked by supabase_uid
  4. All subsequent requests use the JWT directly (no sessions)
"""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import DB, RegisteredUser
from app.config import settings
from app.core.audit import log_event
from app.core.security import TokenError, decode_supabase_token, extract_supabase_uid
from app.models.audit import AuditEventType, AuditLog
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.post import Post
from app.models.proposal import Proposal
from app.models.proposal_comment import ProposalComment
from app.models.signal import Signal, SignalType
from app.models.thread import Thread
from app.models.user import PlatformRole, User, UserTier
from app.schemas.community import CommunityMembershipSummary
from app.schemas.facilitator_request import FacilitatorRequestCreate, FacilitatorRequestOut
from app.schemas.user import CommunityActivityOut, DisplayNameUpdate, MyActivityOut, UserCreate, UserMe, UserPublic

router = APIRouter()


@router.post("/register", response_model=UserMe, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DB) -> dict:
    """
    Create a User record. Called once after Supabase Auth signup.
    The supabase_uid links our record to Supabase's identity.
    """
    existing = await db.execute(
        select(User).where(User.supabase_uid == payload.supabase_uid)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already registered.",
        )

    user = User(
        supabase_uid=payload.supabase_uid,
        email=payload.email,
        display_name=payload.display_name,
    )
    db.add(user)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.USER_REGISTERED,
        target_type="user",
        target_id=user.id,
        payload={"display_name": user.display_name, "tier": user.tier.value},
        actor_id=user.id,
    )

    return {
        "id": user.id,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "tier": user.tier,
        "identity_verified_at": user.identity_verified_at,
        "email": user.email,
        "is_annotator": user.is_annotator,
        "is_platform_admin": user.platform_role == PlatformRole.PLATFORM_ADMIN,
        "display_name_changes_this_month": 0,
        "display_name_changes_remaining": 3,
        "community_memberships": [],
    }


DISPLAY_NAME_CHANGE_LIMIT = 3
DISPLAY_NAME_WINDOW_DAYS = 30


async def _count_display_name_changes(db: DB, user_id) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=DISPLAY_NAME_WINDOW_DAYS)
    result = await db.execute(
        select(func.count()).where(
            AuditLog.actor_id == user_id,
            AuditLog.event_type == AuditEventType.DISPLAY_NAME_CHANGED,
            AuditLog.created_at >= since,
        )
    )
    return result.scalar_one()


async def _get_community_memberships(db: DB, user_id) -> list[CommunityMembershipSummary]:
    """Load active community memberships for a user, joined with community name/slug."""
    result = await db.execute(
        select(Community.slug, Community.name, CommunityMembership.tier)
        .join(Community, Community.id == CommunityMembership.community_id)
        .where(
            CommunityMembership.user_id == user_id,
            CommunityMembership.is_active == True,
        )
        .order_by(CommunityMembership.joined_at.asc())
    )
    return [
        CommunityMembershipSummary(
            community_slug=slug,
            community_name=name,
            tier=tier,
        )
        for slug, name, tier in result.all()
    ]


@router.get("/me", response_model=UserMe)
async def me(user: RegisteredUser, db: DB) -> dict:
    """Return the authenticated user's own record with display name change counts."""
    changes = await _count_display_name_changes(db, user.id)
    memberships = await _get_community_memberships(db, user.id)
    return {
        "id": user.id,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "tier": user.tier,
        "identity_verified_at": user.identity_verified_at,
        "email": user.email,
        "is_annotator": user.is_annotator,
        "is_platform_admin": user.platform_role == PlatformRole.PLATFORM_ADMIN,
        "display_name_changes_this_month": changes,
        "display_name_changes_remaining": max(0, DISPLAY_NAME_CHANGE_LIMIT - changes),
        "community_memberships": memberships,
    }


@router.patch("/me", response_model=UserMe)
async def update_me(payload: DisplayNameUpdate, user: RegisteredUser, db: DB) -> dict:
    """Update the authenticated user's display name (max 3 times per 30 days)."""
    changes = await _count_display_name_changes(db, user.id)

    if changes >= DISPLAY_NAME_CHANGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Display name can only be changed {DISPLAY_NAME_CHANGE_LIMIT} times per 30 days. You have used all {DISPLAY_NAME_CHANGE_LIMIT}.",
        )

    old_name = user.display_name
    user.display_name = payload.display_name
    db.add(user)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.DISPLAY_NAME_CHANGED,
        target_type="user",
        target_id=user.id,
        payload={"old_display_name": old_name, "new_display_name": user.display_name},
        actor_id=user.id,
    )

    memberships = await _get_community_memberships(db, user.id)
    new_changes = changes + 1
    return {
        "id": user.id,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "tier": user.tier,
        "identity_verified_at": user.identity_verified_at,
        "email": user.email,
        "is_annotator": user.is_annotator,
        "is_platform_admin": user.platform_role == PlatformRole.PLATFORM_ADMIN,
        "display_name_changes_this_month": new_changes,
        "display_name_changes_remaining": max(0, DISPLAY_NAME_CHANGE_LIMIT - new_changes),
        "community_memberships": memberships,
    }


@router.post(
    "/facilitator-request",
    response_model=FacilitatorRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_facilitator_request(
    payload: FacilitatorRequestCreate,
    user: RegisteredUser,
    db: DB,
) -> FacilitatorRequest:
    """Submit an application for facilitator status in a community."""
    if user.has_tier(UserTier.FACILITATOR):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have facilitator tier or higher.",
        )

    existing = await db.execute(
        select(FacilitatorRequest).where(
            FacilitatorRequest.user_id == user.id,
            FacilitatorRequest.status == FacilitatorRequestStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending facilitator request.",
        )

    req = FacilitatorRequest(
        user_id=user.id,
        reason=payload.reason,
        community_id=payload.community_id,
    )
    db.add(req)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.FACILITATOR_REQUEST_SUBMITTED,
        target_type="facilitator_request",
        target_id=req.id,
        payload={"user_id": str(user.id)},
        actor_id=user.id,
        community_id=payload.community_id,
    )
    return req


@router.get("/facilitator-request", response_model=FacilitatorRequestOut | None)
async def get_my_facilitator_request(
    user: RegisteredUser,
    db: DB,
) -> FacilitatorRequest | None:
    """Return the user's most recent facilitator request (any status), or null."""
    result = await db.execute(
        select(FacilitatorRequest)
        .where(FacilitatorRequest.user_id == user.id)
        .order_by(FacilitatorRequest.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/me/activity", response_model=MyActivityOut)
async def get_my_activity(user: RegisteredUser, db: DB) -> dict:
    """Return per-community engagement stats: post/comment counts and aggregate signals received."""
    # Load memberships with joined_at and community UUID for subqueries
    memberships_result = await db.execute(
        select(Community.id, Community.slug, Community.name, CommunityMembership.tier, CommunityMembership.joined_at)
        .join(Community, Community.id == CommunityMembership.community_id)
        .where(
            CommunityMembership.user_id == user.id,
            CommunityMembership.is_active == True,
        )
        .order_by(CommunityMembership.joined_at.asc())
    )
    memberships = memberships_result.all()

    communities_out = []
    for community_id, slug, name, tier, joined_at in memberships:
        # Thread IDs for this community
        thread_ids_result = await db.execute(
            select(Thread.id).where(Thread.community_id == community_id)
        )
        thread_ids = [row[0] for row in thread_ids_result.all()]

        post_count = 0
        proposal_ids: list = []
        proposal_comment_count = 0

        if thread_ids:
            # Count user's non-removed posts in this community
            post_count_result = await db.execute(
                select(func.count()).where(
                    Post.author_id == user.id,
                    Post.thread_id.in_(thread_ids),
                    Post.is_removed == False,
                )
            )
            post_count = post_count_result.scalar_one()

            # Get user's proposal IDs in this community
            proposals_result = await db.execute(
                select(Proposal.id).where(
                    Proposal.created_by_id == user.id,
                    Proposal.thread_id.in_(thread_ids),
                )
            )
            proposal_ids = [row[0] for row in proposals_result.all()]

        if proposal_ids:
            # Count user's non-removed proposal comments on their community's proposals
            # (also count comments by user on any proposals in this community)
            comment_count_result = await db.execute(
                select(func.count()).where(
                    ProposalComment.author_id == user.id,
                    ProposalComment.proposal_id.in_(proposal_ids),
                    ProposalComment.is_removed == False,
                )
            )
            proposal_comment_count = comment_count_result.scalar_one()

        # Aggregate signals received on user's posts and proposals in this community,
        # excluding signals the user cast on their own content.
        signals_received: dict[str, int] = {t.value: 0 for t in SignalType}

        if thread_ids:
            # Signals on user's posts
            post_ids_result = await db.execute(
                select(Post.id).where(
                    Post.author_id == user.id,
                    Post.thread_id.in_(thread_ids),
                    Post.is_removed == False,
                )
            )
            post_ids = [row[0] for row in post_ids_result.all()]

            if post_ids:
                post_signals_result = await db.execute(
                    select(Signal.signal_type, func.count()).where(
                        Signal.target_type == "post",
                        Signal.target_id.in_(post_ids),
                        Signal.user_id != user.id,
                    ).group_by(Signal.signal_type)
                )
                for sig_type, count in post_signals_result.all():
                    signals_received[sig_type.value] += count

        if proposal_ids:
            # Signals on user's proposals
            proposal_signals_result = await db.execute(
                select(Signal.signal_type, func.count()).where(
                    Signal.target_type == "proposal",
                    Signal.target_id.in_(proposal_ids),
                    Signal.user_id != user.id,
                ).group_by(Signal.signal_type)
            )
            for sig_type, count in proposal_signals_result.all():
                signals_received[sig_type.value] += count

        communities_out.append(CommunityActivityOut(
            community_slug=slug,
            community_name=name,
            membership_tier=tier,
            joined_at=joined_at,
            post_count=post_count,
            proposal_comment_count=proposal_comment_count,
            signals_received=signals_received,
        ))

    return {"communities": communities_out}


@router.post("/me/password-reset", status_code=status.HTTP_204_NO_CONTENT)
async def request_password_reset(user: RegisteredUser, db: DB) -> Response:
    """Send a password reset email via Supabase for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/recover",
            json={"email": user.email},
            headers={"apikey": settings.SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send reset email. Please try again.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_account(user: RegisteredUser, db: DB) -> Response:
    """Soft-delete the authenticated user's account."""
    user.is_active = False
    db.add(user)
    await db.flush()
    await log_event(
        db,
        event_type=AuditEventType.USER_DEACTIVATED,
        target_type="user",
        target_id=user.id,
        payload={},
        actor_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
