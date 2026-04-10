"""
FastAPI dependency injection for authentication and authorization.

Flow:
  1. Mobile client calls Supabase Auth → gets JWT
  2. Client sends JWT as Bearer token
  3. deps.py verifies JWT locally (no network call)
  4. deps.py loads our User record from DB by supabase_uid
  5. Route functions declare which tier is required via get_participant, etc.
"""

from typing import Annotated, Optional

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_supabase_token, extract_supabase_uid
from app.db.session import get_db
from app.models.user import User, UserTier

log = structlog.get_logger()
bearer = HTTPBearer()
bearer_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        claims = decode_supabase_token(credentials.credentials)
        uid = extract_supabase_uid(claims)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.supabase_uid == uid))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not registered. Call POST /api/v1/auth/register first.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user


async def get_optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """Returns the current user if a valid token is present, otherwise None."""
    if not credentials:
        return None
    try:
        claims = decode_supabase_token(credentials.credentials)
        uid = extract_supabase_uid(claims)
    except TokenError:
        return None
    result = await db.execute(select(User).where(User.supabase_uid == uid))
    return result.scalar_one_or_none()


def _require_tier(required: UserTier):
    async def check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user.has_tier(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires tier '{required.value}' or higher.",
            )
        return user

    return check


# Tier-gated dependencies — use these in route signatures
get_registered = _require_tier(UserTier.REGISTERED)
get_participant = _require_tier(UserTier.PARTICIPANT)
get_facilitator = _require_tier(UserTier.FACILITATOR)
get_admin = _require_tier(UserTier.ADMIN)

# Annotation capability dependency — is_annotator flag OR admin tier
async def get_annotator(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.has_annotator_capability():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires annotator capability.",
        )
    return user


# Type aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
RegisteredUser = Annotated[User, Depends(get_registered)]
ParticipantUser = Annotated[User, Depends(get_participant)]
FacilitatorUser = Annotated[User, Depends(get_facilitator)]
AdminUser = Annotated[User, Depends(get_admin)]
AnnotatorUser = Annotated[User, Depends(get_annotator)]
OptionalUser = Annotated[Optional[User], Depends(get_optional_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
