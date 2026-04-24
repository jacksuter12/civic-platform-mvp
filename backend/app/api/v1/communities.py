"""
Community routes — the primary organizational unit of the platform.

All deliberation lives inside a community. These routes handle:
  - Listing and viewing communities (public, no auth required for public communities)
  - Creating communities (platform admin only)
  - Joining communities (any authenticated user, unless invite-only)
  - Viewing members (public if community.is_public)
  - Community-scoped audit log
"""

import uuid
from datetime import datetime, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DB,
    CurrentUser,
    CommunityAdminUser,
    OptionalUser,
    PlatformAdminUser,
    get_community,
)
from app.core.audit import log_event
from app.models.audit import AuditEventType, AuditLog
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.thread import Thread, ThreadStatus
from app.models.user import PlatformRole, User, UserTier
from app.schemas.audit import AuditLogEntry, AuditLogPage
from app.schemas.community import CommunityCreate, CommunityMemberAdd, CommunityMemberRead, CommunityRead, CommunityUpdate

router = APIRouter()

# Thread statuses that do NOT count as active deliberations
_INACTIVE_STATUSES = (ThreadStatus.CLOSED, ThreadStatus.ARCHIVED)


async def _build_community_read(community: Community, db: AsyncSession) -> CommunityRead:
    """Compute member_count and active_thread_count, return CommunityRead."""
    member_count_result = await db.execute(
        select(func.count()).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.is_active == True,
        )
    )
    member_count = member_count_result.scalar_one()

    active_thread_count_result = await db.execute(
        select(func.count()).where(
            Thread.community_id == community.id,
            Thread.status.notin_(_INACTIVE_STATUSES),
        )
    )
    active_thread_count = active_thread_count_result.scalar_one()

    return CommunityRead(
        id=community.id,
        created_at=community.created_at,
        slug=community.slug,
        name=community.name,
        description=community.description,
        community_type=community.community_type,
        boundary_desc=community.boundary_desc,
        verification_method=community.verification_method,
        is_public=community.is_public,
        is_invite_only=community.is_invite_only,
        is_active=community.is_active,
        member_count=member_count,
        active_thread_count=active_thread_count,
    )


# ---------------------------------------------------------------------------
# GET /communities
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CommunityRead])
async def list_communities(
    db: DB,
    user: OptionalUser,
) -> list[CommunityRead]:
    """
    List active communities.
    - Unauthenticated users and regular members see is_public=TRUE only.
    - Platform admins see all active communities including private ones.
    """
    is_platform_admin = user is not None and user.platform_role == PlatformRole.PLATFORM_ADMIN

    q = select(Community).where(Community.is_active == True)
    if not is_platform_admin:
        q = q.where(Community.is_public == True)
    q = q.order_by(Community.name.asc())

    result = await db.execute(q)
    communities = list(result.scalars())

    return [await _build_community_read(c, db) for c in communities]


# ---------------------------------------------------------------------------
# POST /communities — create (platform admin only)
# ---------------------------------------------------------------------------


@router.post("", response_model=CommunityRead, status_code=status.HTTP_201_CREATED)
async def create_community(
    payload: CommunityCreate,
    admin: PlatformAdminUser,
    db: DB,
) -> CommunityRead:
    """Create a new community. Platform admin only."""
    existing = await db.execute(select(Community).where(Community.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A community with this slug already exists.",
        )

    community = Community(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        community_type=payload.community_type,
        boundary_desc=payload.boundary_desc,
        verification_method=payload.verification_method,
        is_public=payload.is_public,
        is_invite_only=payload.is_invite_only,
        default_phase_durations=payload.default_phase_durations,
        created_by_id=admin.id,
    )
    db.add(community)
    await db.flush()

    default_domain = Domain(
        community_id=community.id,
        slug="general",
        name="General",
        description="Default discussion domain for this community.",
        is_active=True,
    )
    db.add(default_domain)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.COMMUNITY_CREATED,
        target_type="community",
        target_id=community.id,
        payload={
            "slug": community.slug,
            "name": community.name,
            "community_type": community.community_type.value,
        },
        actor_id=admin.id,
        community_id=community.id,
    )

    return await _build_community_read(community, db)


# ---------------------------------------------------------------------------
# PATCH /communities/{slug} — update (platform admin only)
# ---------------------------------------------------------------------------


@router.patch("/{slug}", response_model=CommunityRead)
async def update_community(
    payload: CommunityUpdate,
    community: Annotated[Community, Depends(get_community)],
    admin: PlatformAdminUser,
    db: DB,
) -> CommunityRead:
    """Update community settings. Platform admin only."""
    changes = payload.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(community, field, value)
    db.add(community)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.COMMUNITY_UPDATED,
        target_type="community",
        target_id=community.id,
        payload={"changes": {k: str(v) for k, v in changes.items()}},
        actor_id=admin.id,
        community_id=community.id,
    )

    return await _build_community_read(community, db)


# ---------------------------------------------------------------------------
# GET /communities/{slug}
# ---------------------------------------------------------------------------


@router.get("/{slug}", response_model=CommunityRead)
async def get_community_detail(
    community: Annotated[Community, Depends(get_community)],
    db: DB,
    user: OptionalUser,
) -> CommunityRead:
    """
    Community detail including member_count and active_thread_count.
    Private communities return 404 to unauthenticated users.
    """
    is_platform_admin = user is not None and user.platform_role == PlatformRole.PLATFORM_ADMIN
    if not community.is_public and not is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Community not found.",
        )

    return await _build_community_read(community, db)


# ---------------------------------------------------------------------------
# GET /communities/{slug}/members
# ---------------------------------------------------------------------------


@router.get("/{slug}/members", response_model=list[CommunityMemberRead])
async def list_community_members(
    community: Annotated[Community, Depends(get_community)],
    db: DB,
    user: OptionalUser,
) -> list[CommunityMemberRead]:
    """
    Public member list: display_name + tier only (no email/PII).
    Returns 404 for private communities to unauthenticated users.
    """
    is_platform_admin = user is not None and user.platform_role == PlatformRole.PLATFORM_ADMIN
    if not community.is_public and not is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Community not found.",
        )

    result = await db.execute(
        select(User.display_name, CommunityMembership.tier)
        .join(User, User.id == CommunityMembership.user_id)
        .where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.is_active == True,
        )
        .order_by(CommunityMembership.joined_at.asc())
    )
    rows = result.all()
    return [CommunityMemberRead(display_name=display_name, tier=tier) for display_name, tier in rows]


# ---------------------------------------------------------------------------
# POST /communities/{slug}/join
# ---------------------------------------------------------------------------


@router.post("/{slug}/join", response_model=CommunityRead, status_code=status.HTTP_200_OK)
async def join_community(
    community: Annotated[Community, Depends(get_community)],
    user: CurrentUser,
    db: DB,
) -> CommunityRead:
    """
    Join a community at 'registered' tier.
    Idempotent — existing active membership returns 200 with no side effects.
    Returns 403 if the community is invite-only.
    """
    if community.is_invite_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This community is invite-only.",
        )

    existing = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == user.id,
        )
    )
    membership = existing.scalar_one_or_none()

    if membership is not None:
        if not membership.is_active:
            membership.is_active = True
            db.add(membership)
            await db.flush()
        # Already a member — idempotent, no audit event
        return await _build_community_read(community, db)

    membership = CommunityMembership(
        community_id=community.id,
        user_id=user.id,
        tier=UserTier.REGISTERED,
        joined_at=datetime.now(UTC),
    )
    db.add(membership)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.COMMUNITY_MEMBER_JOINED,
        target_type="community_membership",
        target_id=membership.id,
        payload={"community_id": str(community.id), "user_id": str(user.id)},
        actor_id=user.id,
        community_id=community.id,
    )

    return await _build_community_read(community, db)


# ---------------------------------------------------------------------------
# POST /communities/{slug}/members — admin add member
# ---------------------------------------------------------------------------


@router.post("/{slug}/members", response_model=CommunityMemberRead, status_code=status.HTTP_201_CREATED)
async def admin_add_member(
    payload: CommunityMemberAdd,
    community: Annotated[Community, Depends(get_community)],
    admin: CommunityAdminUser,
    db: DB,
) -> CommunityMemberRead:
    """
    Admin adds a user to a community by email. Community facilitator/admin or platform admin only.
    Creates the membership if it doesn't exist, or updates the tier if it does.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found with that email address.",
        )

    existing = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == target_user.id,
        )
    )
    membership = existing.scalar_one_or_none()

    if membership is None:
        membership = CommunityMembership(
            community_id=community.id,
            user_id=target_user.id,
            tier=payload.tier,
            joined_at=datetime.now(UTC),
        )
        db.add(membership)
        await db.flush()
        await log_event(
            db,
            event_type=AuditEventType.COMMUNITY_MEMBER_JOINED,
            target_type="community_membership",
            target_id=membership.id,
            payload={"tier": payload.tier.value, "added_by_admin": True},
            actor_id=admin.id,
            community_id=community.id,
        )
    else:
        membership.tier = payload.tier
        membership.is_active = True
        db.add(membership)
        await db.flush()
        await log_event(
            db,
            event_type=AuditEventType.COMMUNITY_MEMBER_PROMOTED,
            target_type="community_membership",
            target_id=membership.id,
            payload={"new_tier": payload.tier.value, "promoted_by_admin": True},
            actor_id=admin.id,
            community_id=community.id,
        )

    return CommunityMemberRead(display_name=target_user.display_name, tier=payload.tier)


# ---------------------------------------------------------------------------
# GET /communities/{slug}/audit
# ---------------------------------------------------------------------------


@router.get("/{slug}/audit", response_model=AuditLogPage)
async def community_audit_log(
    community: Annotated[Community, Depends(get_community)],
    db: DB,
    user: OptionalUser,
    event_type: Annotated[AuditEventType | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    """
    Audit log scoped to this community's events.
    Public if community.is_public; 404 for private communities without auth.
    """
    is_platform_admin = user is not None and user.platform_role == PlatformRole.PLATFORM_ADMIN
    if not community.is_public and not is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Community not found.",
        )

    q = select(AuditLog).where(AuditLog.community_id == community.id)
    if event_type:
        q = q.where(AuditLog.event_type == event_type)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
    if target_id:
        q = q.where(AuditLog.target_id == target_id)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    q = q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    entries = [AuditLogEntry.model_validate(row) for row in result.scalars()]

    return AuditLogPage(entries=entries, total=total, limit=limit, offset=offset)
