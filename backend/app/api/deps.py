"""
FastAPI dependency injection for authentication and authorization.

Flow:
  1. Mobile client calls Supabase Auth → gets JWT
  2. Client sends JWT as Bearer token
  3. deps.py verifies JWT locally (no network call)
  4. deps.py loads our User record from DB by supabase_uid
  5. Route functions declare which tier is required via get_participant, etc.
"""

import uuid
from typing import Annotated, Optional

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_supabase_token, extract_supabase_uid
from app.db.session import get_db
from app.models.community import Community
from app.models.community_membership import CommunityMembership
from app.models.user import PlatformRole, User, UserTier, TIER_ORDER

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


async def _get_platform_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Requires platform_role == PLATFORM_ADMIN."""
    if user.platform_role != PlatformRole.PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires platform admin role.",
        )
    return user


async def get_community(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Community:
    """Resolve a Community from the {slug} path parameter. 404 if not found or inactive."""
    result = await db.execute(
        select(Community).where(Community.slug == slug, Community.is_active == True)
    )
    community = result.scalar_one_or_none()
    if community is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found.")
    return community


def community_tier_required(min_tier: UserTier):
    """
    Dependency factory: resolves the community from the {slug} path parameter
    and checks that the current user has at least min_tier membership in it.
    Platform admins bypass this check and pass unconditionally.
    """
    async def check(
        slug: str,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        # Platform admins can act in any community at any tier
        if user.platform_role == PlatformRole.PLATFORM_ADMIN:
            return user

        # Resolve the community
        comm_result = await db.execute(
            select(Community).where(Community.slug == slug, Community.is_active == True)
        )
        community = comm_result.scalar_one_or_none()
        if community is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found."
            )

        # Check membership tier
        mem_result = await db.execute(
            select(CommunityMembership).where(
                CommunityMembership.community_id == community.id,
                CommunityMembership.user_id == user.id,
                CommunityMembership.is_active == True,
            )
        )
        membership = mem_result.scalar_one_or_none()

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this community.",
            )

        if TIER_ORDER[membership.tier] < TIER_ORDER[min_tier]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{min_tier.value}' tier or higher in this community.",
            )
        return user

    return check


async def check_community_membership(
    user: "User",
    community_id: uuid.UUID,
    min_tier: "UserTier",
    db: AsyncSession,
) -> None:
    """
    Inline community membership check for routes where the community is resolved
    from the action target (thread, proposal, etc.) rather than a {slug} path param.

    Platform admins bypass all community checks unconditionally.
    Raises HTTP 403 if the user is not an active member at min_tier or higher.
    """
    if user.platform_role == PlatformRole.PLATFORM_ADMIN:
        return

    result = await db.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community_id,
            CommunityMembership.user_id == user.id,
            CommunityMembership.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this community.",
        )
    if TIER_ORDER[membership.tier] < TIER_ORDER[min_tier]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires '{min_tier.value}' tier or higher in this community.",
        )


# Type aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
RegisteredUser = Annotated[User, Depends(get_registered)]
ParticipantUser = Annotated[User, Depends(get_participant)]
FacilitatorUser = Annotated[User, Depends(get_facilitator)]
AdminUser = Annotated[User, Depends(get_admin)]
AnnotatorUser = Annotated[User, Depends(get_annotator)]
OptionalUser = Annotated[Optional[User], Depends(get_optional_user)]
PlatformAdminUser = Annotated[User, Depends(_get_platform_admin)]
# Community-scoped: facilitator+ tier in the {slug} community, OR platform admin
CommunityAdminUser = Annotated[User, Depends(community_tier_required(UserTier.FACILITATOR))]
DB = Annotated[AsyncSession, Depends(get_db)]
