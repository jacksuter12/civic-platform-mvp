from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AdminUser, DB
from app.models.domain import Domain

router = APIRouter()


class DomainCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", max_length=60)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)


class DomainOut(BaseModel):
    model_config = {"from_attributes": True}
    id: object
    slug: str
    name: str
    description: str
    is_active: bool


@router.get("", response_model=list[DomainOut])
async def list_domains(db: DB) -> list[Domain]:
    result = await db.execute(
        select(Domain).where(Domain.is_active == True).order_by(Domain.name)
    )
    return list(result.scalars())


@router.get("/{slug}", response_model=DomainOut)
async def get_domain(slug: str, db: DB) -> Domain:
    result = await db.execute(select(Domain).where(Domain.slug == slug))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found.")
    return domain


@router.post("", response_model=DomainOut, status_code=status.HTTP_201_CREATED)
async def create_domain(payload: DomainCreate, _admin: AdminUser, db: DB) -> Domain:
    existing = await db.execute(select(Domain).where(Domain.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slug already exists."
        )
    domain = Domain(**payload.model_dump())
    db.add(domain)
    await db.flush()
    return domain
