import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.models.user import UserTier
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema


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
    """Extended self-view including email."""

    email: str


class UserTierUpdate(CamelBase):
    """Admin-only: change a user's tier."""

    user_id: uuid.UUID
    new_tier: UserTier
    reason: str = Field(min_length=10, max_length=500)
