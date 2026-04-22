import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class UserTier(str, PyEnum):
    REGISTERED = "registered"    # email verified; can read threads and cast signals
    PARTICIPANT = "participant"   # identity verified; can post and vote
    FACILITATOR = "facilitator"  # can advance thread phases and moderate posts
    ADMIN = "admin"              # system administration


TIER_ORDER = {
    UserTier.REGISTERED: 0,
    UserTier.PARTICIPANT: 1,
    UserTier.FACILITATOR: 2,
    UserTier.ADMIN: 3,
}


class PlatformRole(str, PyEnum):
    USER = "user"                  # default — no platform-level privileges
    PLATFORM_ADMIN = "platform_admin"  # can create communities, manage annotators


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    supabase_uid: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    tier: Mapped[UserTier] = mapped_column(
        SAEnum(UserTier, name="user_tier"), default=UserTier.REGISTERED, nullable=False
    )
    identity_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Orthogonal capability flag — independent of the registered/participant/facilitator/admin
    # tier hierarchy. A user can be any tier and either have or not have this flag.
    # Admin tier implicitly carries annotator capability; see has_annotator_capability().
    is_annotator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Platform-level role — orthogonal to the tier hierarchy.
    # PLATFORM_ADMIN can create communities and manage platform-wide annotators.
    # Seeded from tier='admin' users in migration a3b4c5d6e7f8.
    platform_role: Mapped[PlatformRole] = mapped_column(
        SAEnum(PlatformRole, name="platform_role"),
        nullable=False,
        default=PlatformRole.USER,
    )

    # Relationships
    threads_created: Mapped[list["Thread"]] = relationship(  # type: ignore[name-defined]
        "Thread", back_populates="created_by", foreign_keys="Thread.created_by_id"
    )
    posts: Mapped[list["Post"]] = relationship(  # type: ignore[name-defined]
        "Post", back_populates="author"
    )
    signals: Mapped[list["Signal"]] = relationship(  # type: ignore[name-defined]
        "Signal", back_populates="user"
    )
    votes: Mapped[list["Vote"]] = relationship(  # type: ignore[name-defined]
        "Vote", back_populates="voter"
    )
    proposals: Mapped[list["Proposal"]] = relationship(  # type: ignore[name-defined]
        "Proposal", back_populates="created_by"
    )
    annotations: Mapped[list["Annotation"]] = relationship(  # type: ignore[name-defined]
        "Annotation", back_populates="author", foreign_keys="Annotation.author_id"
    )
    annotation_reactions: Mapped[list["AnnotationReaction"]] = relationship(  # type: ignore[name-defined]
        "AnnotationReaction", back_populates="user"
    )

    def has_tier(self, required: UserTier) -> bool:
        return TIER_ORDER[self.tier] >= TIER_ORDER[required]

    def has_annotator_capability(self) -> bool:
        """
        Returns True if the user may create and react to annotations.
        Admin tier implicitly carries this capability without requiring
        is_annotator=True to be set explicitly.
        """
        return self.is_annotator or self.tier == UserTier.ADMIN
