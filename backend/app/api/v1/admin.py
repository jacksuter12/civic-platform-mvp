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

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, PlatformAdminUser
from app.core.audit import log_event
from app.core.notifications import create_notification
from app.models.annotator_request import AnnotatorRequest, AnnotatorRequestStatus
from app.models.audit import AuditEventType
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.notification import NotificationType
from app.models.user import PlatformRole, User, UserTier, TIER_ORDER
from app.schemas.annotation import (
    AnnotatorGrantBody,
    UserAdminSummary,
    UserAnnotatorOut,
    UserSyntheticOut,
    UserSyntheticSet,
)
from app.schemas.annotator_request import AnnotatorRequestDetail
from app.schemas.facilitator_request import FacilitatorRequestDetail

log = structlog.get_logger()
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

    try:
        await create_notification(
            db,
            recipient_id=req.user_id,
            notification_type=NotificationType.FACILITATOR_REQUEST_DECIDED,
            actor_id=user.id,
            target_type="facilitator_request",
            target_id=req.id,
            community_id=req.community_id,
            headline="Your facilitator request was approved",
            link="/account",
        )
    except Exception:
        log.warning(
            "notification_failed",
            notification_type="facilitator_request_decided",
            exc_info=True,
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

    try:
        await create_notification(
            db,
            recipient_id=req.user_id,
            notification_type=NotificationType.FACILITATOR_REQUEST_DECIDED,
            actor_id=user.id,
            target_type="facilitator_request",
            target_id=req.id,
            community_id=req.community_id,
            headline="Your facilitator request was denied",
            link="/account",
        )
    except Exception:
        log.warning(
            "notification_failed",
            notification_type="facilitator_request_decided",
            exc_info=True,
        )

    await db.refresh(req, ["user"])
    return FacilitatorRequestDetail.model_validate(req)


# ---------------------------------------------------------------------------
# Annotator requests — list / approve / deny  (platform admin only)
# ---------------------------------------------------------------------------


@router.get("/annotator-requests", response_model=list[AnnotatorRequestDetail])
async def list_annotator_requests(
    admin: PlatformAdminUser,
    db: DB,
) -> list[AnnotatorRequestDetail]:
    """List pending annotator requests. Platform admin only."""
    result = await db.execute(
        select(AnnotatorRequest)
        .where(AnnotatorRequest.status == AnnotatorRequestStatus.PENDING)
        .order_by(AnnotatorRequest.created_at.asc())
    )
    requests = list(result.scalars())
    out = []
    for req in requests:
        await db.refresh(req, ["user"])
        out.append(AnnotatorRequestDetail.model_validate(req))
    return out


@router.post(
    "/annotator-requests/{request_id}/approve",
    response_model=AnnotatorRequestDetail,
)
async def approve_annotator_request(
    request_id: uuid.UUID,
    admin: PlatformAdminUser,
    db: DB,
) -> AnnotatorRequestDetail:
    """Approve an annotator request — sets is_annotator=True on the user."""
    result = await db.execute(
        select(AnnotatorRequest).where(AnnotatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != AnnotatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    req.status = AnnotatorRequestStatus.APPROVED
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.now(UTC)
    db.add(req)

    user_result = await db.execute(select(User).where(User.id == req.user_id))
    target_user = user_result.scalar_one()
    target_user.is_annotator = True
    db.add(target_user)

    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATOR_REQUEST_APPROVED,
        target_type="annotator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=admin.id,
    )
    await log_event(
        db,
        event_type=AuditEventType.USER_ANNOTATOR_GRANTED,
        target_type="user",
        target_id=req.user_id,
        payload={"via": "annotator_request", "request_id": str(req.id)},
        actor_id=admin.id,
    )

    await db.refresh(req, ["user"])
    return AnnotatorRequestDetail.model_validate(req)


@router.post(
    "/annotator-requests/{request_id}/deny",
    response_model=AnnotatorRequestDetail,
)
async def deny_annotator_request(
    request_id: uuid.UUID,
    admin: PlatformAdminUser,
    db: DB,
) -> AnnotatorRequestDetail:
    """Deny an annotator request. Platform admin only."""
    result = await db.execute(
        select(AnnotatorRequest).where(AnnotatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != AnnotatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    req.status = AnnotatorRequestStatus.DENIED
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.now(UTC)
    db.add(req)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATOR_REQUEST_DENIED,
        target_type="annotator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=admin.id,
    )

    await db.refresh(req, ["user"])
    return AnnotatorRequestDetail.model_validate(req)


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
# Synthetic (bot) account marking — platform admin only
# ---------------------------------------------------------------------------


@router.post("/users/synthetic", response_model=UserSyntheticOut)
async def set_user_synthetic(
    payload: UserSyntheticSet,
    admin: PlatformAdminUser,
    db: DB,
) -> UserSyntheticOut:
    """
    Mark an account as operated by software, or clear the mark. Platform admin
    only, and deliberately not settable at registration: POST /auth/register is
    unauthenticated, so a self-asserted label would be worth nothing. This way
    the claim has an accountable author, recorded in the audit log.

    Idempotent — no audit entry when the value is already what you asked for.

    Keyed by email rather than id so a seeding script can call it without
    having captured the id, which it does not have on the already-exists path.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404, detail="No user found with that email address."
        )

    if target.is_synthetic == payload.is_synthetic:
        return UserSyntheticOut(
            id=target.id,
            display_name=target.display_name,
            is_synthetic=target.is_synthetic,
        )

    target.is_synthetic = payload.is_synthetic
    db.add(target)
    await db.flush()

    audit_payload: dict = {}
    if payload.reason:
        audit_payload["reason"] = payload.reason

    await log_event(
        db,
        event_type=(
            AuditEventType.USER_MARKED_SYNTHETIC
            if payload.is_synthetic
            else AuditEventType.USER_UNMARKED_SYNTHETIC
        ),
        target_type="user",
        target_id=target.id,
        payload=audit_payload,
        actor_id=admin.id,
    )

    return UserSyntheticOut(
        id=target.id,
        display_name=target.display_name,
        is_synthetic=target.is_synthetic,
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
            is_synthetic=u.is_synthetic,
            created_at=u.created_at,
        )
        for u in users
    ]
