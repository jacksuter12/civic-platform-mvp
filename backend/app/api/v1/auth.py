"""
Auth routes: register our User record after Supabase Auth signup.

Flow:
  1. User signs up via Supabase Auth (magic link or OAuth)
  2. Client calls POST /auth/register with the JWT and display_name
  3. We create the User record linked by supabase_uid
  4. All subsequent requests use the JWT directly (no sessions)
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB, RegisteredUser
from app.core.audit import log_event
from app.core.security import TokenError, decode_supabase_token, extract_supabase_uid
from app.models.audit import AuditEventType, AuditLog
from app.models.user import User
from app.schemas.user import DisplayNameUpdate, UserCreate, UserMe, UserPublic

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


DISPLAY_NAME_CHANGE_LIMIT = 3
DISPLAY_NAME_WINDOW_DAYS = 30


async def _count_display_name_changes(db: DB, user_id) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=DISPLAY_NAME_WINDOW_DAYS)
    result = await db.execute(
        select(func.count()).where(
            AuditLog.actor_id == user_id,
            AuditLog.event_type == AuditEventType.DISPLAY_NAME_CHANGED,
            AuditLog.created_at >= since,
        )
    )
    return result.scalar_one()


@router.get("/me", response_model=UserMe)
async def me(user: RegisteredUser, db: DB) -> dict:
    """Return the authenticated user's own record with display name change counts."""
    changes = await _count_display_name_changes(db, user.id)
    data = {
        "id": user.id,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "tier": user.tier,
        "identity_verified_at": user.identity_verified_at,
        "email": user.email,
        "display_name_changes_this_month": changes,
        "display_name_changes_remaining": max(0, DISPLAY_NAME_CHANGE_LIMIT - changes),
    }
    return data


@router.patch("/me", response_model=UserMe)
async def update_me(payload: DisplayNameUpdate, user: RegisteredUser, db: DB) -> dict:
    """Update the authenticated user's display name (max 3 times per 30 days)."""
    changes = await _count_display_name_changes(db, user.id)

    if changes >= DISPLAY_NAME_CHANGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Display name can only be changed {DISPLAY_NAME_CHANGE_LIMIT} times per 30 days. You have used all {DISPLAY_NAME_CHANGE_LIMIT}.",
        )

    old_name = user.display_name
    user.display_name = payload.display_name
    db.add(user)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.DISPLAY_NAME_CHANGED,
        target_type="user",
        target_id=user.id,
        payload={"old_display_name": old_name, "new_display_name": user.display_name},
        actor_id=user.id,
    )

    new_changes = changes + 1
    return {
        "id": user.id,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "tier": user.tier,
        "identity_verified_at": user.identity_verified_at,
        "email": user.email,
        "display_name_changes_this_month": new_changes,
        "display_name_changes_remaining": max(0, DISPLAY_NAME_CHANGE_LIMIT - new_changes),
    }
