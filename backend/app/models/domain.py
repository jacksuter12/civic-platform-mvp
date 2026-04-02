from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Domain(Base, UUIDPKMixin, TimestampMixin):
    """
    A topical area for deliberation (e.g., "healthcare", "housing").
    Domains are domain-agnostic by design; healthcare is the initial focus.
    """

    __tablename__ = "domains"

    slug: Mapped[str] = mapped_column(
        String(60), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    threads: Mapped[list["Thread"]] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="domain"
    )
    pools: Mapped[list["FundingPool"]] = relationship(  # type: ignore[name-defined]
        "FundingPool", back_populates="domain"
    )
