import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.models.user import UserTier
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.community import CommunityMembershipSummary


class ActivityItem(CamelBase):
    """A single post or proposal comment in the user's activity history."""

    item_type: str
    id: uuid.UUID
    body: str
    created_at: datetime
    is_removed: bool
    thread_id: uuid.UUID
    thread_title: str
    thread_status: str
    community_slug: str
    community_name: str
    proposal_id: uuid.UUID | None = None
    proposal_title: str | None = None


class MyHistoryOut(CamelBase):
    items: list[ActivityItem]
    total: int
    limit: int
    offset: int


class CommunityActivityOut(CamelBase):
    """Per-community engagement summary for a user's account page."""

    community_slug: str
    community_name: str
    membership_tier: UserTier
    joined_at: datetime
    post_count: int
    proposal_comment_count: int
    signals_received: dict[str, int]


class MyActivityOut(CamelBase):
    communities: list[CommunityActivityOut]


class UserCreate(CamelBase):
    """Payload sent on first registration after Supabase auth."""

    supabase_uid: str
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=60)

    @field_validator("display_name")
    @classmethod
    def no_pii_patterns(cls, v: str) -> str:
        # Prevent full names; encourage handles or first-name-only
        if len(v.split()) > 3:
            raise ValueError("Display name must not look like a full name")
        return v.strip()


class UserPublic(UUIDSchema, TimestampSchema):
    """Safe public representation — no email, no supabase_uid."""

    display_name: str
    tier: UserTier
    identity_verified_at: datetime | None


class UserMe(UserPublic):
    """Extended self-view including email and community memberships."""

    email: str
    display_name_changes_this_month: int = 0
    display_name_changes_remaining: int = 3
    is_annotator: bool = False
    is_platform_admin: bool = False
    community_memberships: list[CommunityMembershipSummary] = []


class DisplayNameUpdate(CamelBase):
    display_name: str = Field(min_length=2, max_length=60)

    @field_validator("display_name")
    @classmethod
    def no_pii_patterns(cls, v: str) -> str:
        if len(v.split()) > 3:
            raise ValueError("Display name must not look like a full name")
        return v.strip()


class UserTierUpdate(CamelBase):
    """Admin-only: change a user's tier."""

    user_id: uuid.UUID
    new_tier: UserTier
    reason: str = Field(min_length=10, max_length=500)
