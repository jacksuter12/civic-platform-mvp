import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class FundingPool(Base, UUIDPKMixin, TimestampMixin):
    """
    A pool of funds (simulated in MVP) available for allocation via proposals.

    In MVP: currency is "USD_SIM" — no real money moves.
    Future: connect to real grant disbursement, community chest, etc.

    Invariant: allocated_amount <= total_amount (enforced at application layer).
    """

    __tablename__ = "funding_pools"

    domain_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total_amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=14, scale=2), nullable=False
    )
    allocated_amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=14, scale=2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(
        String(16), nullable=False, default="USD_SIM"
    )
    pool_opens_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    pool_closes_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    domain: Mapped["Domain"] = relationship(  # type: ignore[name-defined]
        "Domain", back_populates="pools"
    )
    allocations: Mapped[list["AllocationDecision"]] = relationship(  # type: ignore[name-defined]
        "AllocationDecision", back_populates="pool"
    )

    @property
    def remaining_amount(self) -> Decimal:
        return self.total_amount - self.allocated_amount
