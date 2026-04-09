"""
Annotation schemas — minimal shapes for prompt 2 (data model layer).
Prompt 3 (API routes) will expand these with full validation, nested
UserPublic fields, reaction counts, and list/pagination responses.
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.models.annotation import AnnotationTargetType, ReactionType
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema

# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


class AnnotationCreate(CamelBase):
    target_type: AnnotationTargetType
    target_id: str = Field(min_length=1, max_length=255)
    # anchor_data is opaque JSON from the Hypothesis anchoring library.
    # Prompt 3 may add structural validation if needed; for now accept any dict.
    anchor_data: dict
    parent_id: uuid.UUID | None = None
    body: str = Field(min_length=1, max_length=5000)


class AnnotationUpdate(CamelBase):
    """Author edits the body. anchor_data is immutable after creation."""

    body: str = Field(min_length=1, max_length=5000)


class AnnotationRead(UUIDSchema, TimestampSchema):
    target_type: AnnotationTargetType
    target_id: str
    anchor_data: dict
    author_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str
    updated_at: datetime | None
    deleted_at: datetime | None
    # Prompt 3 will add: author: UserPublic, reactions: list[AnnotationReactionRead]


# ---------------------------------------------------------------------------
# AnnotationReaction
# ---------------------------------------------------------------------------


class AnnotationReactionCreate(CamelBase):
    reaction: ReactionType


class AnnotationReactionRead(UUIDSchema, TimestampSchema):
    annotation_id: uuid.UUID
    user_id: uuid.UUID
    reaction: ReactionType
