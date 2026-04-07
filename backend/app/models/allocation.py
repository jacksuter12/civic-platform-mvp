import uuid
from decimal import Decimal

from sqlalchemy import DECIMAL, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AllocationDecision(Base, UUIDPKMixin, TimestampMixin):
    """
    Records a final allocation of funds from a pool to a proposal.

    Immutable once created. The rationale and vote_summary are written
    at decision time and never updated — they form the transparency record.

    Invariant: proposal.status must be PASSED before allocation is recorded.
    """

    __tablename__ = "allocation_decisions"

    pool_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("funding_pools.id"), nullable=False
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("proposals.id"),
        nullable=False,
        unique=True,  # one allocation per proposal
    )
    decided_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=14, scale=2), nullable=False
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # Snapshot of vote tallies at decision time — never recalculated
    vote_summary: Mapped[dict] = mapped_column(JSON, nullable=False)

    pool: Mapped["FundingPool"] = relationship(  # type: ignore[name-defined]
        "FundingPool", back_populates="allocations"
    )
    proposal: Mapped["Proposal"] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="allocation"
    )
    decided_by: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
