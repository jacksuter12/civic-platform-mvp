import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.user import UserTier


class CommunityMembership(Base, UUIDPKMixin, TimestampMixin):
    """
    Records that a user belongs to a community at a given tier.
    One row per (community, user) pair — enforced by UNIQUE constraint.

    tier mirrors UserTier but is scoped to this community. A user can be a
    facilitator in one community and registered in another.

    verified_at / verified_by_id: optional — set when a community admin
    manually verifies the membership (e.g., confirmed residency for a
    geographic community).
    """

    __tablename__ = "community_memberships"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_community_membership_user"),
    )

    community_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("communities.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    tier: Mapped[UserTier] = mapped_column(
        SAEnum(UserTier, name="user_tier"), nullable=False, default=UserTier.REGISTERED
    )
    # joined_at is the moment the user became a member (may differ from created_at
    # for back-filled historical memberships)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    community: Mapped["Community"] = relationship(  # type: ignore[name-defined]
        "Community", back_populates="memberships"
    )
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[user_id]
    )
    verified_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[verified_by_id]
    )
