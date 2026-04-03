import uuid
from datetime import datetime

from pydantic import Field

from app.models.facilitator_request import FacilitatorRequestStatus
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


class FacilitatorRequestCreate(CamelBase):
    reason: str = Field(min_length=10, max_length=500)


class RequestingUser(CamelBase):
    id: uuid.UUID
    display_name: str
    email: str
    tier: str


class FacilitatorRequestOut(UUIDSchema, TimestampSchema):
    """User-facing: their own request status."""

    reason: str
    status: FacilitatorRequestStatus
    reviewed_at: datetime | None = None


class FacilitatorRequestDetail(UUIDSchema, TimestampSchema):
    """Admin-facing: includes requesting user's info."""

    user_id: uuid.UUID
    reason: str
    status: FacilitatorRequestStatus
    reviewed_at: datetime | None = None
    user: RequestingUser
