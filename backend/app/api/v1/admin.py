"""Admin routes — facilitator request review and tier management."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, DB
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.user import User, UserTier
from app.schemas.facilitator_request import FacilitatorRequestDetail

router = APIRouter()


@router.get("/facilitator-requests", response_model=list[FacilitatorRequestDetail])
async def list_facilitator_requests(
    admin: AdminUser,
    db: DB,
) -> list[FacilitatorRequestDetail]:
    """List all pending facilitator requests, oldest first."""
    result = await db.execute(
        select(FacilitatorRequest)
        .where(FacilitatorRequest.status == FacilitatorRequestStatus.PENDING)
        .order_by(FacilitatorRequest.created_at.asc())
    )
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
    admin: AdminUser,
    db: DB,
) -> FacilitatorRequestDetail:
    result = await db.execute(
        select(FacilitatorRequest).where(FacilitatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != FacilitatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    user_result = await db.execute(select(User).where(User.id == req.user_id))
    user = user_result.scalar_one()
    old_tier = user.tier
    user.tier = UserTier.FACILITATOR
    db.add(user)

    req.status = FacilitatorRequestStatus.APPROVED
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.add(req)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.USER_TIER_CHANGED,
        target_type="user",
        target_id=user.id,
        payload={
            "old_tier": old_tier.value,
            "new_tier": UserTier.FACILITATOR.value,
            "reason": "facilitator_request_approved",
        },
        actor_id=admin.id,
    )
    await log_event(
        db,
        event_type=AuditEventType.FACILITATOR_REQUEST_APPROVED,
        target_type="facilitator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=admin.id,
    )

    await db.refresh(req, ["user"])
    return FacilitatorRequestDetail.model_validate(req)


@router.post(
    "/facilitator-requests/{request_id}/deny",
    response_model=FacilitatorRequestDetail,
)
async def deny_facilitator_request(
    request_id: uuid.UUID,
    admin: AdminUser,
    db: DB,
) -> FacilitatorRequestDetail:
    result = await db.execute(
        select(FacilitatorRequest).where(FacilitatorRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status != FacilitatorRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already reviewed.")

    req.status = FacilitatorRequestStatus.DENIED
    req.reviewed_by_id = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.add(req)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.FACILITATOR_REQUEST_DENIED,
        target_type="facilitator_request",
        target_id=req.id,
        payload={"user_id": str(req.user_id)},
        actor_id=admin.id,
    )

    await db.refresh(req, ["user"])
    return FacilitatorRequestDetail.model_validate(req)
