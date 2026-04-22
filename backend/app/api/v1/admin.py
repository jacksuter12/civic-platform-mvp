"""Admin routes — facilitator request review, tier management, annotator capability.

Authorization model (Session 2):
  - PlatformAdminUser: platform_role == 'platform_admin'
      Can manage annotators, list all users, create communities, approve/deny
      facilitator requests across all communities.
  - CommunityAdminUser (ad-hoc): user has active CommunityMembership with
      tier >= 'facilitator' for the request's community.
      Can approve/deny facilitator requests for their community.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, PlatformAdminUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.user import PlatformRole, User, UserTier, TIER_ORDER
from app.schemas.annotation import AnnotatorGrantBody, UserAdminSummary, UserAnnotatorOut
from app.schemas.facilitator_request import FacilitatorRequestDetail

router = APIRouter()


async def _assert_community_admin(
    user: User,
    community_id: uuid.UUID,
    db,
) -> None:
    """
    Raise 403 if user is neither a platform admin nor a facilitator/admin
    member of the specified community.
    """
    if user.platform_role == PlatformRole.PLATFORM_ADMIN:
        return
    result = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community_id,
            CommunityMembership.user_id == user.id,
            CommunityMembership.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None or TIER_ORDER[membership.tier] < TIER_ORDER[UserTier.FACILITATOR]:
        raise HTTPException(
            status_code=403,
            detail="Requires community admin (facilitator+) role for this community.",
        )


@router.get("/facilitator-requests", response_model=list[FacilitatorRequestDetail])
async def list_facilitator_requests(
    user: CurrentUser,
    db: DB,
    community_slug: str | None = Query(default=None, description="Filter by community slug"),
) -> list[FacilitatorRequestDetail]:
    """
    List pending facilitator requests.
    - Platform admin: sees all pending requests (optionally filtered by community_slug).
    - Community admin: sees only requests for communities where they are facilitator+.
    - Others: 403.
    """
    is_platform_admin = user.platform_role == PlatformRole.PLATFORM_ADMIN

    q = (
        select(FacilitatorRequest)
        .where(FacilitatorRequest.status == FacilitatorRequestStatus.PENDING)
        .order_by(FacilitatorRequest.created_at.asc())
    )

    if is_platform_admin:
        # Platform admin: optionally filter by community slug
        if community_slug:
            comm_result = await db.execute(
                select(Community.id).where(Community.slug == community_slug)
            )
            community_id = comm_result.scalar_one_or_none()
            if community_id is not None:
                q = q.where(FacilitatorRequest.community_id == community_id)
    else:
        # Must be community admin in at least one community
        mem_result = await db.execute(
            select(CommunityMembership.community_id).where(
                CommunityMembership.user_id == user.id,
                CommunityMembership.is_active == True,
                CommunityMembership.tier.in_([UserTier.FACILITATOR, UserTier.ADMIN]),
            )
        )
        admin_community_ids = [row[0] for row in mem_result.all()]
        if not admin_community_ids:
            raise HTTPException(
                status_code=403,
                detail="Requires platform admin or community admin role.",
            )
        q = q.where(FacilitatorRequest.community_id.in_(admin_community_ids))

        # Optionally narrow to a specific community slug
        if community_slug:
            comm_result = await db.execute(
                select(Community.id).where(Community.slug == community_slug)
            )
            cid = comm_result.scalar_one_or_none()
            if cid is not None and cid in admin_community_ids:
                q = q.where(FacilitatorRequest.community_id == cid)

    result = await db.execute(q)
    requests = list(result.scalars())
    out = []
    for req in requests:
        await db.refresh(req, ["user"])
        out.append(FacilitatorRequestDetail.model_validate(req))
    return out


@router.post(
    "/facilitator-requests/{request_id}/approve",
    response_model=FacilitatorRequestDetail,
)
async def approve_facilitator_request(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> FacilitatorRequestDetail:
    """
    Approve a facilitator request.
    - Promotes CommunityMembership.tier to 'facilitator' (creates membership if needed).
    - Requires platform admin OR community admin for the request's community.
    - Logs COMMUNITY_MEMBER_PROMOTED + FACILITATOR_REQUEST_APPROVED.
    """
    result = await db.execute(
        select(FacilitatorRequest).where(FacilitatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != FacilitatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    # Authorization: must be platform admin or community admin for req's community
    if req.community_id is None:
        # Legacy request with no community — only platform admin can approve
        if user.platform_role != PlatformRole.PLATFORM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Requires platform admin role for requests without a community.",
            )
    else:
        await _assert_community_admin(user, req.community_id, db)

    # Mark request approved
    req.status = FacilitatorRequestStatus.APPROVED
    req.reviewed_by_id = user.id
    req.reviewed_at = datetime.now(UTC)
    db.add(req)

    # Promote (or create) CommunityMembership to facilitator tier
    membership = None
    if req.community_id is not None:
        existing_mem = await db.execute(
            select(CommunityMembership).where(
                CommunityMembership.community_id == req.community_id,
                CommunityMembership.user_id == req.user_id,
            )
        )
        membership = existing_mem.scalar_one_or_none()
        if membership is None:
            membership = CommunityMembership(
                community_id=req.community_id,
                user_id=req.user_id,
                tier=UserTier.FACILITATOR,
                joined_at=datetime.now(UTC),
            )
        else:
            membership.tier = UserTier.FACILITATOR
        db.add(membership)

    await db.flush()

    # Log COMMUNITY_MEMBER_PROMOTED if community-scoped
    if req.community_id is not None and membership is not None:
        await log_event(
            db,
            event_type=AuditEventType.COMMUNITY_MEMBER_PROMOTED,
            target_type="community_membership",
            target_id=membership.id,
            payload={"user_id": str(req.user_id), "new_tier": UserTier.FACILITATOR.value},
            actor_id=user.id,
            community_id=req.community_id,
        )

    await log_event(
        db,
        event_type=AuditEventType.FACILITATOR_REQUEST_APPROVED,
        target_type="facilitator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=user.id,
        community_id=req.community_id,
    )

    await db.refresh(req, ["user"])
    return FacilitatorRequestDetail.model_validate(req)


@router.post(
    "/facilitator-requests/{request_id}/deny",
    response_model=FacilitatorRequestDetail,
)
async def deny_facilitator_request(
    request_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> FacilitatorRequestDetail:
    """
    Deny a facilitator request.
    Requires platform admin OR community admin for the request's community.
    """
    result = await db.execute(
        select(FacilitatorRequest).where(FacilitatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != FacilitatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    # Authorization
    if req.community_id is None:
        if user.platform_role != PlatformRole.PLATFORM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Requires platform admin role for requests without a community.",
            )
    else:
        await _assert_community_admin(user, req.community_id, db)

    req.status = FacilitatorRequestStatus.DENIED
    req.reviewed_by_id = user.id
    req.reviewed_at = datetime.now(UTC)
    db.add(req)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.FACILITATOR_REQUEST_DENIED,
        target_type="facilitator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=user.id,
        community_id=req.community_id,
    )

    await db.refresh(req, ["user"])
    return FacilitatorRequestDetail.model_validate(req)


# ---------------------------------------------------------------------------
# Annotator capability — grant / revoke  (platform admin only)
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/annotator", response_model=UserAnnotatorOut)
async def grant_annotator(
    user_id: uuid.UUID,
    admin: PlatformAdminUser,
    db: DB,
    payload: AnnotatorGrantBody | None = None,
) -> UserAnnotatorOut:
    """
    Grant annotator capability to a user. Idempotent — if already set, returns
    current state without writing an audit entry. Platform admin only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.is_annotator:
        return UserAnnotatorOut(
            id=target.id,
            display_name=target.display_name,
            is_annotator=target.is_annotator,
            tier=target.tier,
        )

    target.is_annotator = True
    db.add(target)
    await db.flush()

    audit_payload: dict = {}
    if payload and payload.reason:
        audit_payload["reason"] = payload.reason

    await log_event(
        db,
        event_type=AuditEventType.USER_ANNOTATOR_GRANTED,
        target_type="user",
        target_id=target.id,
        payload=audit_payload,
        actor_id=admin.id,
    )

    return UserAnnotatorOut(
        id=target.id,
        display_name=target.display_name,
        is_annotator=target.is_annotator,
        tier=target.tier,
    )


@router.delete("/users/{user_id}/annotator", response_model=UserAnnotatorOut)
async def revoke_annotator(
    user_id: uuid.UUID,
    admin: PlatformAdminUser,
    db: DB,
    payload: AnnotatorGrantBody | None = None,
) -> UserAnnotatorOut:
    """
    Revoke annotator capability from a user. Idempotent — if already false,
    returns current state without writing an audit entry. Platform admin only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if not target.is_annotator:
        return UserAnnotatorOut(
            id=target.id,
            display_name=target.display_name,
            is_annotator=target.is_annotator,
            tier=target.tier,
        )

    target.is_annotator = False
    db.add(target)
    await db.flush()

    audit_payload: dict = {}
    if payload and payload.reason:
        audit_payload["reason"] = payload.reason

    await log_event(
        db,
        event_type=AuditEventType.USER_ANNOTATOR_REVOKED,
        target_type="user",
        target_id=target.id,
        payload=audit_payload,
        actor_id=admin.id,
    )

    return UserAnnotatorOut(
        id=target.id,
        display_name=target.display_name,
        is_annotator=target.is_annotator,
        tier=target.tier,
    )


# ---------------------------------------------------------------------------
# User list (platform admin only)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserAdminSummary])
async def list_users(
    admin: PlatformAdminUser,
    db: DB,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[UserAdminSummary]:
    """
    Return all registered users, ordered by display_name ascending.
    Optional substring search against display_name or email.
    Platform admin only.
    """
    query = select(User).order_by(User.display_name.asc())
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                User.display_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    users = list(result.scalars())
    return [
        UserAdminSummary(
            id=u.id,
            display_name=u.display_name,
            email=u.email,
            tier=u.tier,
            is_annotator=u.is_annotator,
            created_at=u.created_at,
        )
        for u in users
    ]
