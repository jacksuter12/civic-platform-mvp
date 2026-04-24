import uuid
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import DECIMAL, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProposalStatus(str, PyEnum):
    DRAFT = "draft"              # author is still editing
    SUBMITTED = "submitted"      # ready for facilitator review
    UNDER_REVIEW = "under_review"  # facilitator is reviewing
    VOTING = "voting"            # open for participant votes
    PASSED = "passed"            # vote succeeded
    REJECTED = "rejected"        # vote failed
    IMPLEMENTED = "implemented"  # allocation decision made


class Proposal(Base, UUIDPKMixin, TimestampMixin):
    """
    A formal, actionable proposal that emerges from deliberation.
    Can only be submitted when thread.status == PROPOSING.
    Can only be voted on when thread.status == VOTING.
    """

    __tablename__ = "proposals"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Requested amount from funding pool (None = non-monetary proposal)
    requested_amount: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=12, scale=2), nullable=True
    )
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, name="proposal_status"),
        default=ProposalStatus.DRAFT,
        nullable=False,
        index=True,
    )
    # Incremented on each content edit. Starts at 1 (the live state is always
    # "the current version"). A snapshot of the prior state is written to
    # proposal_versions before each edit.
    current_version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    # Server-rendered HTML from description. Populated on create/edit so the
    # frontend doesn't need a markdown parser. Annotation anchors reference
    # text ranges in this HTML, so rendering must be deterministic.
    body_html: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # Relationships
    thread: Mapped["Thread"] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="proposals"
    )
    created_by: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="proposals"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="proposal"
    )
    allocation: Mapped["AllocationDecision | None"] = relationship(  # type: ignore[name-defined]
        "AllocationDecision", back_populates="proposal", uselist=False
    )
    comments: Mapped[list["ProposalComment"]] = relationship(  # type: ignore[name-defined]
        "ProposalComment", back_populates="proposal", order_by="ProposalComment.created_at"
    )
    amendments: Mapped[list["Amendment"]] = relationship(  # type: ignore[name-defined]
        "Amendment", back_populates="proposal", order_by="Amendment.created_at"
    )
    versions: Mapped[list["ProposalVersion"]] = relationship(  # type: ignore[name-defined]
        "ProposalVersion", back_populates="proposal", order_by="ProposalVersion.version_number"
    )
