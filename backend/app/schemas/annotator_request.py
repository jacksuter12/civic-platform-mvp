import uuid
from datetime import datetime

from pydantic import Field

from app.models.annotator_request import AnnotatorRequestStatus
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


class AnnotatorRequestCreate(CamelBase):
    reason: str | None = Field(default=None, max_length=500)


class RequestingUser(CamelBase):
    id: uuid.UUID
    display_name: str
    email: str
    tier: str


class AnnotatorRequestOut(UUIDSchema, TimestampSchema):
    """User-facing: their own request status."""

    reason: str | None = None
    status: AnnotatorRequestStatus
    reviewed_at: datetime | None = None


class AnnotatorRequestDetail(UUIDSchema, TimestampSchema):
    """Admin-facing: includes requesting user's info."""

    user_id: uuid.UUID
    reason: str | None = None
    status: AnnotatorRequestStatus
    reviewed_at: datetime | None = None
    user: RequestingUser
