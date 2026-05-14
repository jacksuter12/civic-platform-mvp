import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class NotificationType(str, PyEnum):
    POST_REPLY = "post_reply"
    PROPOSAL_CREATED = "proposal_created"
    THREAD_PHASE_ADVANCED = "thread_phase_advanced"
    THREAD_VOTING_OPENED = "thread_voting_opened"
    ANNOTATION_CREATED = "annotation_created"
    FACILITATOR_REQUEST_SUBMITTED = "facilitator_request_submitted"
    FACILITATOR_REQUEST_DECIDED = "facilitator_request_decided"
    MEMBERSHIP_REQUEST_SUBMITTED = "membership_request_submitted"
    MEMBERSHIP_REQUEST_DECIDED = "membership_request_decided"


class Notification(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "notifications"

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # String(60) intentionally — avoids DB enum migrations when types are added
    notification_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("communities.id"), nullable=True
    )
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recipient: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[recipient_id], back_populates="notifications"
    )
    actor: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[actor_id]
    )


class NotificationPreference(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "notification_preferences"
    # A row means that notification_type is DISABLED for that user.
    # No row = enabled (default). Only deviations from default are stored.

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(60), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "notification_type", name="uq_notif_pref_user_type"),)

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[user_id]
    )
