import uuid

from pydantic import Field

from app.models.community import CommunityType
from app.models.user import UserTier
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


class CommunityCreate(CamelBase):
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    community_type: CommunityType
    boundary_desc: str = Field(min_length=10, max_length=500)
    verification_method: str = Field(min_length=5, max_length=500)
    is_public: bool = True
    is_invite_only: bool = False
    default_phase_durations: dict | None = None


class CommunityRead(UUIDSchema, TimestampSchema):
    slug: str
    name: str
    description: str
    community_type: CommunityType
    boundary_desc: str
    verification_method: str
    is_public: bool
    is_invite_only: bool
    is_active: bool
    member_count: int = 0
    active_thread_count: int = 0


class CommunityMemberRead(CamelBase):
    """Public member list — display_name + tier only, no email/PII."""

    display_name: str
    tier: UserTier


class CommunityMembershipSummary(CamelBase):
    """Summary of a community membership for inclusion in user /me responses."""

    community_slug: str
    community_name: str
    tier: UserTier
