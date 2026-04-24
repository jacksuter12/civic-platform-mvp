"""
Annotation schemas — expanded for prompt 3 (API route layer).

Includes:
- AnnotationCreate / AnnotationUpdate  (request bodies)
- AnnotationRead                       (full response with author + reaction counts)
- AnnotationReactionCreate             (request body for POST reactions)
- AnnotationReactionState              (response from POST/DELETE reactions)
- AnnotationReactionRead               (individual reaction row, kept for completeness)
- UserAnnotatorOut                     (admin grant/revoke response)
- AnnotatorGrantBody                   (optional body for grant/revoke)
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.models.annotation import AnnotationTargetType, ReactionType
from app.models.user import UserTier
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic

# ---------------------------------------------------------------------------
# Shared sub-shapes
# ---------------------------------------------------------------------------


class ReactionCounts(CamelBase):
    """Aggregated reaction counts for a single annotation."""

    endorse: int = 0
    needs_work: int = 0


# ---------------------------------------------------------------------------
# Annotation request bodies
# ---------------------------------------------------------------------------


class AnnotationCreate(CamelBase):
    target_type: AnnotationTargetType
    target_id: str = Field(min_length=1, max_length=255)
    # Opaque JSON from the Hypothesis anchoring library.
    anchor_data: dict
    parent_id: uuid.UUID | None = None
    body: str = Field(min_length=1, max_length=5000)


class AnnotationUpdate(CamelBase):
    """Author (or admin) edits the body. anchor_data is immutable after creation."""

    body: str = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Annotation response
# ---------------------------------------------------------------------------


class AnnotationRead(UUIDSchema, TimestampSchema):
    """
    Full annotation response. Reactions are aggregated (counts + requesting user's
    own reaction). Replies are NOT nested — they are returned as flat objects with
    parent_id set; the frontend groups them.
    """

    target_type: AnnotationTargetType
    target_id: str
    anchor_data: dict
    author: UserPublic
    parent_id: uuid.UUID | None
    body: str
    updated_at: datetime | None
    deleted_at: datetime | None
    resolved_at: datetime | None = None
    resolved_by_id: uuid.UUID | None = None
    reactions: ReactionCounts
    my_reaction: ReactionType | None


# ---------------------------------------------------------------------------
# Reaction request / response
# ---------------------------------------------------------------------------


class AnnotationReactionCreate(CamelBase):
    reaction: ReactionType


class AnnotationReactionState(CamelBase):
    """
    Reaction state returned by POST /reactions and used internally.
    Counts by type plus the requesting user's own current reaction.
    """

    endorse: int
    needs_work: int
    my_reaction: ReactionType | None


class AnnotationReactionRead(UUIDSchema, TimestampSchema):
    """Individual reaction row — kept for completeness / future use."""

    annotation_id: uuid.UUID
    user_id: uuid.UUID
    reaction: ReactionType


# ---------------------------------------------------------------------------
# Admin annotator capability
# ---------------------------------------------------------------------------


class UserAnnotatorOut(CamelBase):
    """Minimal user representation returned by annotator grant/revoke endpoints."""

    id: uuid.UUID
    display_name: str
    is_annotator: bool
    tier: UserTier


class AnnotatorGrantBody(CamelBase):
    """Optional request body for annotator grant/revoke — reason is advisory."""

    reason: str | None = Field(default=None, max_length=500)


class UserAdminSummary(CamelBase):
    """User row returned by GET /admin/users."""

    id: uuid.UUID
    display_name: str
    email: str
    tier: UserTier
    is_annotator: bool
    created_at: datetime
