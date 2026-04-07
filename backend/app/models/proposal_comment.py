import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProposalComment(Base, UUIDPKMixin, TimestampMixin):
    """
    A comment on a specific proposal, allowed only during PROPOSING phase.

    Deliberative design choices (mirrors Post):
    - No reactions or upvotes — distribution of sentiment is via Signals.
    - Soft-deleted with recorded reason for facilitator accountability.
    - Threaded (parent_id) but depth capped in UI.
    """

    __tablename__ = "proposal_comments"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("proposal_comments.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    removal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="comments"
    )
    author: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    replies: Mapped[list["ProposalComment"]] = relationship(
        "ProposalComment", back_populates="parent", foreign_keys=[parent_id]
    )
    parent: Mapped["ProposalComment | None"] = relationship(
        "ProposalComment", back_populates="replies", remote_side="ProposalComment.id"
    )
