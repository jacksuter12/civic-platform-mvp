"""
Allocation routes — the final accountability surface.

Allocation records the decision to commit pool funds to a passed proposal.
Invariants enforced here:
  1. Proposal must be in PASSED status.
  2. Pool must have sufficient remaining funds.
  3. Vote summary snapshot is captured at decision time (immutable).
  4. AllocationDecision is append-only; pool.allocated_amount is updated.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from decimal import Decimal

from app.api.deps import AdminUser, DB
from app.core.audit import log_event
from app.models.allocation import AllocationDecision
from app.models.audit import AuditEventType
from app.models.pool import FundingPool
from app.models.proposal import Proposal, ProposalStatus
from app.models.vote import Vote, VoteChoice
from sqlalchemy import func

router = APIRouter()


class AllocationOut(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    pool_id: uuid.UUID
    proposal_id: uuid.UUID
    amount: Decimal
    rationale: str
    vote_summary: dict
    created_at: object


@router.get("", response_model=list[AllocationOut])
async def list_allocations(
    db: DB,
    pool_id: uuid.UUID | None = None,
) -> list[AllocationDecision]:
    q = select(AllocationDecision).order_by(AllocationDecision.created_at.desc())
    if pool_id:
        q = q.where(AllocationDecision.pool_id == pool_id)
    result = await db.execute(q)
    return list(result.scalars())


@router.post("", response_model=AllocationOut, status_code=status.HTTP_201_CREATED)
async def create_allocation(
    payload: "AllocationPayload",
    admin: AdminUser,
    db: DB,
) -> AllocationDecision:
    # Validate proposal
    prop_result = await db.execute(
        select(Proposal).where(Proposal.id == payload.proposal_id)
    )
    proposal = prop_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    if proposal.status != ProposalStatus.PASSED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Proposal must be in 'passed' status. Current: '{proposal.status.value}'.",
        )

    # Validate pool and check remaining funds
    pool_result = await db.execute(
        select(FundingPool).where(FundingPool.id == payload.pool_id)
    )
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found.")
    if pool.remaining_amount < payload.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Insufficient pool funds. Requested: {payload.amount}, "
                f"Available: {pool.remaining_amount}."
            ),
        )

    # Capture vote summary snapshot
    rows = await db.execute(
        select(Vote.choice, func.count(Vote.id))
        .where(Vote.proposal_id == payload.proposal_id)
        .group_by(Vote.choice)
    )
    vote_counts = {row[0].value: row[1] for row in rows}
    vote_summary = {
        "yes": vote_counts.get("yes", 0),
        "no": vote_counts.get("no", 0),
        "abstain": vote_counts.get("abstain", 0),
    }

    # Commit allocation
    allocation = AllocationDecision(
        pool_id=payload.pool_id,
        proposal_id=payload.proposal_id,
        decided_by_id=admin.id,
        amount=payload.amount,
        rationale=payload.rationale,
        vote_summary=vote_summary,
    )
    db.add(allocation)

    # Update pool balance
    pool.allocated_amount += payload.amount

    # Mark proposal as implemented
    proposal.status = ProposalStatus.IMPLEMENTED

    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ALLOCATION_DECIDED,
        target_type="allocation",
        target_id=allocation.id,
        payload={
            "pool_id": str(payload.pool_id),
            "proposal_id": str(payload.proposal_id),
            "amount": str(payload.amount),
            "vote_summary": vote_summary,
            "rationale": payload.rationale,
        },
        actor_id=admin.id,
    )

    return allocation


class AllocationPayload(BaseModel):
    pool_id: uuid.UUID
    proposal_id: uuid.UUID
    amount: Decimal = Field(gt=Decimal("0"))
    rationale: str = Field(min_length=20, max_length=2000)
