import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Domain(Base, UUIDPKMixin, TimestampMixin):
    """
    A topical area for deliberation (e.g., "healthcare", "housing").
    Domains are domain-agnostic by design; healthcare is the initial focus.

    slug is unique within a community (UNIQUE(community_id, slug)), not globally.
    """

    __tablename__ = "domains"
    __table_args__ = (
        UniqueConstraint("community_id", "slug", name="uq_domains_community_slug"),
    )

    # community_id is nullable in the model so that SQLite test fixtures that
    # create Domain without community_id continue to pass during Session 1.
    # The NOT NULL constraint is enforced in PostgreSQL via migration c9d0e1f2a3b4.
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("communities.id"),
        nullable=True,
        index=True,
    )
    slug: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    community: Mapped["Community | None"] = relationship(  # type: ignore[name-defined]
        "Community", back_populates="domains"
    )
    threads: Mapped[list["Thread"]] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="domain"
    )
    pools: Mapped[list["FundingPool"]] = relationship(  # type: ignore[name-defined]
        "FundingPool", back_populates="domain"
    )
