"""
Auth routes: register our User record after Supabase Auth signup.

Flow:
  1. User signs up via Supabase Auth (magic link or OAuth)
  2. Client calls POST /auth/register with the JWT and display_name
  3. We create the User record linked by supabase_uid
  4. All subsequent requests use the JWT directly (no sessions)
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB, RegisteredUser
from app.core.audit import log_event
from app.core.security import TokenError, decode_supabase_token, extract_supabase_uid
from app.models.audit import AuditEventType
from app.models.user import User
from app.schemas.user import UserCreate, UserMe, UserPublic

router = APIRouter()


@router.post("/register", response_model=UserMe, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DB) -> User:
    """
    Create a User record. Called once after Supabase Auth signup.
    The supabase_uid links our record to Supabase's identity.
    """
    existing = await db.execute(
        select(User).where(User.supabase_uid == payload.supabase_uid)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already registered.",
        )

    user = User(
        supabase_uid=payload.supabase_uid,
        email=payload.email,
        display_name=payload.display_name,
    )
    db.add(user)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.USER_REGISTERED,
        target_type="user",
        target_id=user.id,
        payload={"display_name": user.display_name, "tier": user.tier.value},
        actor_id=user.id,
    )

    return user


@router.get("/me", response_model=UserMe)
async def me(user: RegisteredUser) -> User:
    """Return the authenticated user's own record."""
    return user
