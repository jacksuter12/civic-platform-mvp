import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class CommunityType(str, PyEnum):
    GEOGRAPHIC = "geographic"
    ORGANIZATIONAL = "organizational"
    INSTITUTIONAL = "institutional"
    TOPICAL = "topical"
    TECHNICAL = "technical"


class Community(Base, UUIDPKMixin, TimestampMixin):
    """
    Primary organizational unit of the platform. All deliberation happens within
    a community. Community membership (not global tier) gates deliberative actions
    once Session 3 route updates land.

    slug is globally unique — communities are identified by slug in URLs:
    /c/{slug}/threads, /c/{slug}/thread/{id}, etc.
    """

    __tablename__ = "communities"

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    community_type: Mapped[CommunityType] = mapped_column(
        SAEnum(CommunityType, name="community_type"), nullable=False
    )
    boundary_desc: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_invite_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSONB on PostgreSQL (GIN-indexable), JSON on SQLite (tests)
    default_phase_durations: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Nullable: the initial seed community is created with no human creator
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id]
    )
    memberships: Mapped[list["CommunityMembership"]] = relationship(  # type: ignore[name-defined]
        "CommunityMembership", back_populates="community"
    )
    domains: Mapped[list["Domain"]] = relationship(  # type: ignore[name-defined]
        "Domain", back_populates="community"
    )
    threads: Mapped[list["Thread"]] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="community"
    )
