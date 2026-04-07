import uuid
from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class SignalType(str, PyEnum):
    """
    Structured participant sentiment. Replaces free-form reactions.
    Designed to surface the distribution of concern — not to rank posts.
    """

    SUPPORT = "support"       # I support the direction of this discussion
    CONCERN = "concern"       # I have concerns that need addressing
    NEED_INFO = "need_info"   # I need more information before forming a view
    BLOCK = "block"           # I have a strong objection (rare; surfaced prominently)


class SignalTargetType(str, PyEnum):
    """
    Polymorphic target for signals. Stored as a plain string column so adding
    new target types never requires an ALTER TYPE migration.
    """

    THREAD = "thread"
    POST = "post"
    PROPOSAL = "proposal"
    PROPOSAL_COMMENT = "proposal_comment"
    AMENDMENT = "amendment"


class Signal(Base, UUIDPKMixin, TimestampMixin):
    """
    One signal per user per target. Updating replaces prior signal.
    Signals are visible in aggregate (not attributed) to all readers.
    target_id is a polymorphic UUID reference — no FK enforced at DB level.
    """

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_signal_user_target"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_type: Mapped[SignalTargetType] = mapped_column(
        String(60), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    signal_type: Mapped[SignalType] = mapped_column(
        SAEnum(SignalType, name="signal_type"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="signals"
    )
