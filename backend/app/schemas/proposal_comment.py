import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic


class ProposalCommentCreate(CamelBase):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: uuid.UUID | None = None


class ProposalCommentRead(UUIDSchema, TimestampSchema):
    proposal_id: uuid.UUID
    author: UserPublic
    parent_id: uuid.UUID | None
    body: str
    is_removed: bool
    removal_reason: str | None
    updated_at: datetime


class ProposalCommentRemove(CamelBase):
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Recorded in audit log. Required for facilitator accountability.",
    )
