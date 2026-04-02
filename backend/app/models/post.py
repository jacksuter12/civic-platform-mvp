import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Post(Base, UUIDPKMixin, TimestampMixin):
    """
    A contribution to a thread's deliberation.

    Deliberative design choices:
    - No upvotes, downvotes, or reaction counts. Prevents outrage amplification.
    - Displayed chronologically — no algorithmic ranking.
    - Soft-deleted; removal reason recorded for accountability.
    - Threaded replies allowed but depth capped in UI (max 2 levels).
    """

    __tablename__ = "posts"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("posts.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    removal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    thread: Mapped["Thread"] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="posts"
    )
    author: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="posts"
    )
    replies: Mapped[list["Post"]] = relationship(
        "Post", back_populates="parent", foreign_keys=[parent_id]
    )
    parent: Mapped["Post | None"] = relationship(
        "Post", back_populates="replies", remote_side="Post.id"
    )
