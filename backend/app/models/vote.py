import uuid
from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class VoteChoice(str, PyEnum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class Vote(Base, UUIDPKMixin, TimestampMixin):
    """
    Votes are cast on proposals, not posts.
    This is a deliberate design choice: the deliberation phase builds
    shared understanding; the voting phase records collective will.

    One vote per participant per proposal. Cannot be changed after casting.
    Rationale is optional but encouraged.
    """

    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("proposal_id", "voter_id", name="uq_vote_proposal_voter"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False, index=True
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    choice: Mapped[VoteChoice] = mapped_column(
        SAEnum(VoteChoice, name="vote_choice"), nullable=False
    )
    rationale: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="votes"
    )
    voter: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="votes"
    )
