import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.models.amendment import AmendmentStatus
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic


class AmendmentCreate(CamelBase):
    title: str = Field(min_length=5, max_length=200)
    original_text: str = Field(
        min_length=10,
        description="The specific passage from the proposal being amended.",
    )
    proposed_text: str = Field(
        min_length=10,
        description="The replacement text the author proposes.",
    )
    rationale: str = Field(
        min_length=10,
        max_length=1000,
        description="Why this change improves the proposal.",
    )


class AmendmentRead(UUIDSchema, TimestampSchema):
    proposal_id: uuid.UUID
    author: UserPublic
    title: str
    original_text: str
    proposed_text: str
    rationale: str
    status: AmendmentStatus
    reviewed_at: datetime | None
    updated_at: datetime


class AmendmentReview(CamelBase):
    """Proposal author accepts or rejects an amendment."""

    status: AmendmentStatus
    reviewer_note: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def must_be_terminal(cls, v: AmendmentStatus) -> AmendmentStatus:
        if v == AmendmentStatus.PENDING:
            raise ValueError("Review status must be 'accepted' or 'rejected', not 'pending'.")
        return v
