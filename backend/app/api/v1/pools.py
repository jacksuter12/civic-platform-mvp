import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DB, check_community_membership
from app.models.community import Community
from app.models.domain import Domain
from app.models.pool import FundingPool
from app.models.user import UserTier

router = APIRouter()


class PoolCreate(BaseModel):
    domain_id: uuid.UUID
    name: str = Field(min_length=5, max_length=120)
    description: str = Field(default="", max_length=2000)
    total_amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD_SIM", max_length=16)
    pool_opens_at: datetime
    pool_closes_at: datetime


class PoolOut(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    community_id: uuid.UUID | None
    domain_id: uuid.UUID
    name: str
    description: str
    total_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    currency: str
    pool_opens_at: datetime
    pool_closes_at: datetime
    created_at: datetime


@router.get("", response_model=list[PoolOut])
async def list_pools(
    db: DB,
    community_slug: Annotated[str, Query()],
    domain_slug: Annotated[str | None, Query()] = None,
) -> list[FundingPool]:
    # Resolve community
    comm_result = await db.execute(
        select(Community).where(Community.slug == community_slug, Community.is_active == True)
    )
    community = comm_result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found.")

    q = select(FundingPool).where(FundingPool.community_id == community.id)

    if domain_slug:
        dr = await db.execute(
            select(Domain).where(
                Domain.slug == domain_slug,
                Domain.community_id == community.id,
            )
        )
        domain = dr.scalar_one_or_none()
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found.")
        q = q.where(FundingPool.domain_id == domain.id)

    result = await db.execute(q.order_by(FundingPool.pool_opens_at.desc()))
    return list(result.scalars())


@router.post("", response_model=PoolOut, status_code=status.HTTP_201_CREATED)
async def create_pool(payload: PoolCreate, user: CurrentUser, db: DB) -> FundingPool:
    if payload.pool_closes_at <= payload.pool_opens_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pool_closes_at must be after pool_opens_at.",
        )

    # Resolve community from domain
    domain_result = await db.execute(
        select(Domain).where(Domain.id == payload.domain_id, Domain.is_active == True)
    )
    domain = domain_result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found or inactive.")

    if domain.community_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Domain has no community; cannot create pool.",
        )

    # Community admin (facilitator+) required to create pools
    await check_community_membership(user, domain.community_id, UserTier.ADMIN, db)

    pool = FundingPool(
        community_id=domain.community_id,
        **payload.model_dump(),
    )
    db.add(pool)
    await db.flush()
    return pool
