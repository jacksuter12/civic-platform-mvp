import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from typing import Annotated

from app.api.deps import AdminUser, DB
from app.models.domain import Domain
from app.models.pool import FundingPool

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
    domain_slug: Annotated[str | None, Query()] = None,
) -> list[FundingPool]:
    q = select(FundingPool)
    if domain_slug:
        dr = await db.execute(select(Domain).where(Domain.slug == domain_slug))
        domain = dr.scalar_one_or_none()
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found.")
        q = q.where(FundingPool.domain_id == domain.id)
    result = await db.execute(q.order_by(FundingPool.pool_opens_at.desc()))
    return list(result.scalars())


@router.post("", response_model=PoolOut, status_code=status.HTTP_201_CREATED)
async def create_pool(payload: PoolCreate, _admin: AdminUser, db: DB) -> FundingPool:
    if payload.pool_closes_at <= payload.pool_opens_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pool_closes_at must be after pool_opens_at.",
        )
    pool = FundingPool(**payload.model_dump())
    db.add(pool)
    await db.flush()
    return pool
