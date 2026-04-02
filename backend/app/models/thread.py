import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ThreadStatus(str, PyEnum):
    """
    Phase-gated state machine. Each transition is logged to audit_logs.
    Only facilitators may advance phases.

    OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED

    Anti-outrage design: users cannot jump ahead or re-open phases.
    No algorithmic ranking — posts shown chronologically.
    """

    OPEN = "open"                  # accepting all posts
    DELIBERATING = "deliberating"  # structured turn-based discussion
    PROPOSING = "proposing"        # participants submit formal proposals
    VOTING = "voting"              # participants vote on proposals
    CLOSED = "closed"              # results visible, no new actions
    ARCHIVED = "archived"          # historical record only


VALID_TRANSITIONS: dict[ThreadStatus, list[ThreadStatus]] = {
    ThreadStatus.OPEN: [ThreadStatus.DELIBERATING],
    ThreadStatus.DELIBERATING: [ThreadStatus.PROPOSING],
    ThreadStatus.PROPOSING: [ThreadStatus.VOTING],
    ThreadStatus.VOTING: [ThreadStatus.CLOSED],
    ThreadStatus.CLOSED: [ThreadStatus.ARCHIVED],
    ThreadStatus.ARCHIVED: [],
}


class Thread(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "threads"

    domain_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ThreadStatus] = mapped_column(
        SAEnum(ThreadStatus, name="thread_status"),
        default=ThreadStatus.OPEN,
        nullable=False,
        index=True,
    )
    phase_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    domain: Mapped["Domain"] = relationship(  # type: ignore[name-defined]
        "Domain", back_populates="threads"
    )
    created_by: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="threads_created", foreign_keys=[created_by_id]
    )
    posts: Mapped[list["Post"]] = relationship(  # type: ignore[name-defined]
        "Post", back_populates="thread", order_by="Post.created_at"
    )
    signals: Mapped[list["Signal"]] = relationship(  # type: ignore[name-defined]
        "Signal", back_populates="thread"
    )
    proposals: Mapped[list["Proposal"]] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="thread"
    )

    def can_advance_to(self, next_status: ThreadStatus) -> bool:
        return next_status in VALID_TRANSITIONS[self.status]
