import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AmendmentStatus(str, PyEnum):
    PENDING = "pending"    # awaiting review by proposal author
    ACCEPTED = "accepted"  # proposal author signals intent to incorporate
    REJECTED = "rejected"  # proposal author declines


class Amendment(Base, UUIDPKMixin, TimestampMixin):
    """
    A proposed change to a specific section of a proposal.

    Constraints:
    - Only participants who did NOT create the proposal may submit amendments.
    - Only the proposal's author may accept or reject an amendment.
    - Acceptance is a signal of intent; it does NOT automatically rewrite the
      proposal text. The proposer must manually revise their proposal.
    - Only allowed while thread.status == PROPOSING.
    """

    __tablename__ = "amendments"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[AmendmentStatus] = mapped_column(
        SAEnum(AmendmentStatus, name="amendment_status"),
        default=AmendmentStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="amendments"
    )
    author: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
