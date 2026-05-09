import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class MembershipRequestStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class MembershipRequest(Base, UUIDPKMixin, TimestampMixin):
    """
    Self-service join request for invite-only communities.
    Only created when Community.allow_membership_requests is True.
    One pending request per (community, user) pair — enforced by unique constraint.
    """

    __tablename__ = "membership_requests"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_membership_request_user"),
    )

    community_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("communities.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MembershipRequestStatus] = mapped_column(
        SAEnum(MembershipRequestStatus, name="membership_request_status"),
        default=MembershipRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    community: Mapped["Community"] = relationship(  # type: ignore[name-defined]
        "Community"
    )
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[user_id]
    )
    reviewed_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[reviewed_by_id]
    )
