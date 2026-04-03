import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class FacilitatorRequestStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class FacilitatorRequest(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "facilitator_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[FacilitatorRequestStatus] = mapped_column(
        SAEnum(FacilitatorRequestStatus, name="facilitator_request_status"),
        default=FacilitatorRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[user_id]
    )
    reviewed_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[reviewed_by_id]
    )
