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


class Signal(Base, UUIDPKMixin, TimestampMixin):
    """
    One signal per user per thread. Updating replaces prior signal.
    Signals are visible in aggregate (not attributed) to all readers.
    """

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("thread_id", "user_id", name="uq_signal_thread_user"),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    signal_type: Mapped[SignalType] = mapped_column(
        SAEnum(SignalType, name="signal_type"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)

    thread: Mapped["Thread"] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="signals"
    )
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="signals"
    )
