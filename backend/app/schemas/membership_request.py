import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.membership_request import MembershipRequestStatus
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


class MembershipRequestCreate(CamelBase):
    reason: str | None = Field(default=None, max_length=500)


class MembershipRequestReview(CamelBase):
    action: Literal["approve", "deny"]


class RequestingUser(CamelBase):
    id: uuid.UUID
    display_name: str
    email: str


class MembershipRequestOut(UUIDSchema, TimestampSchema):
    """User-facing: their own request status."""

    community_id: uuid.UUID
    reason: str | None = None
    status: MembershipRequestStatus
    reviewed_at: datetime | None = None


class MembershipRequestDetail(UUIDSchema, TimestampSchema):
    """Admin-facing: includes requesting user's info."""

    community_id: uuid.UUID
    user_id: uuid.UUID
    reason: str | None = None
    status: MembershipRequestStatus
    reviewed_at: datetime | None = None
    user: RequestingUser
