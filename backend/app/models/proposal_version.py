import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProposalVersionStatus(str, enum.Enum):
    accepted = "accepted"    # currently authoritative or historically so
    suggested = "suggested"  # proposed change, not yet decided (Chunk B)
    rejected = "rejected"    # proposed change declined (Chunk B)
    withdrawn = "withdrawn"  # editor withdrew before decision (Chunk B)


class ProposalVersion(Base, UUIDPKMixin, TimestampMixin):
    """
    Immutable snapshot of a proposal's content taken before each edit.

    Design intent:
    - Written once, never updated or deleted.
    - version_number corresponds to the proposal's current_version_number
      at the time the snapshot was taken (i.e. the state being replaced).
    - Allows full reconstruction of the proposal's edit history.
    - Pairs with audit_logs: each PROPOSAL_EDITED audit entry references
      the version_number that was archived.

    Track Changes fields (status, authored_by_id, parent_version_id,
    decided_at, decided_by_id, decision_reason) are forward-compat stubs
    for Chunk B. All existing versions default to status='accepted'.
    """

    __tablename__ = "proposal_versions"
    __table_args__ = (
        UniqueConstraint("proposal_id", "version_number", name="uq_proposal_version"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    edit_summary: Mapped[str] = mapped_column(String(500), nullable=False)

    # --- Track Changes forward-compat fields (Chunk B feature, data only) ---
    status: Mapped[ProposalVersionStatus] = mapped_column(
        SAEnum(ProposalVersionStatus, name="proposal_version_status"),
        nullable=False,
        server_default="accepted",
    )
    authored_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("proposal_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="versions"
    )
    author: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[author_id]
    )
    authored_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[authored_by_id]
    )
    decided_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[decided_by_id]
    )
