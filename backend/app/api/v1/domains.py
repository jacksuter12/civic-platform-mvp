import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, PlatformAdminUser
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.user import PlatformRole, UserTier

router = APIRouter()


class DomainCreate(BaseModel):
    community_id: uuid.UUID
    slug: str = Field(pattern=r"^[a-z0-9-]+$", max_length=60)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)


class DomainOut(BaseModel):
    model_config = {"from_attributes": True}
    id: object
    community_id: uuid.UUID | None
    slug: str
    name: str
    description: str
    is_active: bool


@router.get("", response_model=list[DomainOut])
async def list_domains(
    db: DB,
    community_slug: Annotated[str, Query()],
) -> list[Domain]:
    # Resolve community
    comm_result = await db.execute(
        select(Community).where(Community.slug == community_slug, Community.is_active == True)
    )
    community = comm_result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found.")

    result = await db.execute(
        select(Domain)
        .where(Domain.community_id == community.id, Domain.is_active == True)
        .order_by(Domain.name)
    )
    return list(result.scalars())


@router.get("/{slug}", response_model=DomainOut)
async def get_domain(
    slug: str,
    db: DB,
    community_slug: Annotated[str, Query()],
) -> Domain:
    # Resolve community
    comm_result = await db.execute(
        select(Community).where(Community.slug == community_slug, Community.is_active == True)
    )
    community = comm_result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found.")

    result = await db.execute(
        select(Domain).where(Domain.slug == slug, Domain.community_id == community.id)
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found.")
    return domain


@router.post("", response_model=DomainOut, status_code=status.HTTP_201_CREATED)
async def create_domain(
    payload: DomainCreate, user: CurrentUser, db: DB
) -> Domain:
    # Validate community exists
    comm_result = await db.execute(
        select(Community).where(Community.id == payload.community_id, Community.is_active == True)
    )
    if not comm_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Community not found.")

    # Platform admin OR facilitator/admin of the target community
    if user.platform_role != PlatformRole.PLATFORM_ADMIN:
        membership = await db.execute(
            select(CommunityMembership).where(
                CommunityMembership.user_id == user.id,
                CommunityMembership.community_id == payload.community_id,
                CommunityMembership.tier.in_([UserTier.FACILITATOR, UserTier.ADMIN]),
                CommunityMembership.is_active == True,
            )
        )
        if not membership.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Facilitator or admin role in this community required.",
            )

    existing = await db.execute(
        select(Domain).where(
            Domain.community_id == payload.community_id,
            Domain.slug == payload.slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug already exists in this community.",
        )
    domain = Domain(
        community_id=payload.community_id,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
    )
    db.add(domain)
    await db.flush()
    return domain
