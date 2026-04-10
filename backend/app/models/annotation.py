import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AnnotationTargetType(str, PyEnum):
    """
    Allowed values for annotation.target_type.
    Stored as plain String(60) — not a DB enum — so adding new target
    types never requires an ALTER TYPE migration. (Same pattern as SignalTargetType.)
    v1 ships on wiki only; post/proposal/document are reserved for future use.
    """

    WIKI = "wiki"
    POST = "post"
    PROPOSAL = "proposal"
    DOCUMENT = "document"


class ReactionType(str, PyEnum):
    """
    Two editorial reaction types. Explicitly NOT upvote/downvote.
    Reaction counts are display-only; they must never influence sort order,
    ranking, or content visibility. See decisions.md 2026-04-09.
    """

    ENDORSE = "endorse"
    NEEDS_WORK = "needs_work"


class Annotation(Base, UUIDPKMixin, TimestampMixin):
    """
    An inline annotation anchored to a text range (or section fallback) within
    a target document. Target-agnostic: target_type + target_id identify any
    content object. v1 target_type is always 'wiki'.

    Soft-deleted only (deleted_at is set; body tombstoned by the API layer).
    Replies are one level deep — enforced in the API layer, not here.
    """

    __tablename__ = "annotations"
    __table_args__ = (
        # Primary query pattern: fetch all annotations on a given target.
        Index("ix_annotations_target_type_id", "target_type", "target_id"),
    )

    # Polymorphic target — string, not UUID, because wiki targets are slugs.
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Opaque JSON from the Hypothesis anchoring libraries. The backend stores
    # and returns this verbatim; only the frontend interprets it.
    # with_variant: JSONB on PostgreSQL (GIN-indexable), JSON on SQLite (tests).
    anchor_data: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )

    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # Nullable: top-level annotations have no parent; replies point to one.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("annotations.id"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Set by the API layer on edit. Null means never edited.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft delete. When set, the API layer replaces body with a tombstone marker.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ---
    author: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="annotations"
    )
    parent: Mapped["Annotation | None"] = relationship(
        "Annotation", back_populates="replies", remote_side="Annotation.id"
    )
    replies: Mapped[list["Annotation"]] = relationship(
        "Annotation", back_populates="parent", foreign_keys=[parent_id]
    )
    reactions: Mapped[list["AnnotationReaction"]] = relationship(
        "AnnotationReaction", back_populates="annotation", cascade="all, delete-orphan"
    )


class AnnotationReaction(Base, UUIDPKMixin, TimestampMixin):
    """
    One reaction per user per annotation (endorse or needs_work).
    Changing a reaction is an upsert — handled by the API layer.
    ON DELETE CASCADE: reactions disappear if the parent annotation is hard-deleted
    (only possible by a DB admin; application layer soft-deletes only).
    """

    __tablename__ = "annotation_reactions"
    __table_args__ = (
        UniqueConstraint(
            "annotation_id", "user_id", name="uq_annotation_reaction_user"
        ),
    )

    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("annotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reaction: Mapped[ReactionType] = mapped_column(
        SAEnum(ReactionType, name="reaction_type"), nullable=False
    )

    # --- Relationships ---
    annotation: Mapped["Annotation"] = relationship(
        "Annotation", back_populates="reactions"
    )
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="annotation_reactions"
    )
