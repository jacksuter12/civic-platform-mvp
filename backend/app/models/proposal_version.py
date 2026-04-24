import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


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

    # Relationships
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="versions"
    )
    author: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
