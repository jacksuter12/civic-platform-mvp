"""
Tests for the community API (Session 2).

Authorization rules validated here:
  - Platform admin can create community; non-admin gets 403.
  - Join creates a registered membership; double-join is idempotent.
  - Invite-only community returns 403 on join attempt.
  - Community audit log returns only that community's events.
  - Platform audit log returns only NULL-community events.
  - Community admin can approve facilitator request → CommunityMembership promoted.
  - Platform admin can approve any community's facilitator request.
  - Non-admin cannot approve facilitator request.
"""

import uuid
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.audit import AuditEventType, AuditLog
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.user import PlatformRole, User, UserTier


# ---------------------------------------------------------------------------
# Fixtures: shared data
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="redlands",
        name="City of Redlands",
        description="Civic deliberation for Redlands, CA residents.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="City of Redlands, San Bernardino County, CA",
        verification_method="Email domain verification",
        is_public=True,
        is_invite_only=False,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def private_community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="private-group",
        name="Private Group",
        description="An invite-only private community for testing.",
        community_type=CommunityType.ORGANIZATIONAL,
        boundary_desc="Internal group only",
        verification_method="Manual invite",
        is_public=False,
        is_invite_only=True,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def platform_admin(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-platform-admin",
        email="platform-admin@example.com",
        display_name="PlatformAdmin",
        tier=UserTier.ADMIN,
        platform_role=PlatformRole.PLATFORM_ADMIN,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-regular",
        email="regular@example.com",
        display_name="RegularUser",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def community_admin(db_session: AsyncSession, community: Community) -> User:
    """A user with facilitator-tier membership in the test community."""
    u = User(
        supabase_uid="uid-community-admin",
        email="community-admin@example.com",
        display_name="CommunityAdmin",
        tier=UserTier.FACILITATOR,
    )
    db_session.add(u)
    await db_session.flush()

    membership = CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=UserTier.FACILITATOR,
        joined_at=datetime.now(UTC),
    )
    db_session.add(membership)
    await db_session.commit()
    return u


# ---------------------------------------------------------------------------
# Client helpers — override get_current_user so we don't need real JWTs
# ---------------------------------------------------------------------------


def _make_client(db_session: AsyncSession, user: User | None = None):
    """
    Return an AsyncClient context manager with auth and DB overridden.
    Overrides both get_current_user and get_optional_user so routes that
    accept optional auth (OptionalUser) also see the correct user.
    """

    async def override_db():
        yield db_session

    async def override_required_user():
        if user is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    async def override_optional_user():
        return user  # None for unauthenticated, User object otherwise

    overrides: dict = {
        get_db: override_db,
        get_optional_user: override_optional_user,
    }
    if user is not None:
        overrides[get_current_user] = override_required_user

    app.dependency_overrides.update(overrides)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests: community creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_can_create_community(
    db_session: AsyncSession, platform_admin: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(
            "/api/v1/communities",
            json={
                "slug": "new-city",
                "name": "New City",
                "description": "A new community for testing creation.",
                "community_type": "geographic",
                "boundary_desc": "New City, State boundary description here",
                "verification_method": "Email verification process",
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "new-city"
    assert data["name"] == "New City"
    assert data["member_count"] == 0


@pytest.mark.asyncio
async def test_non_admin_cannot_create_community(
    db_session: AsyncSession, regular_user: User
) -> None:
    async with _make_client(db_session, regular_user) as c:
        resp = await c.post(
            "/api/v1/communities",
            json={
                "slug": "blocked",
                "name": "Blocked",
                "description": "Should not be created by non-admin.",
                "community_type": "topical",
                "boundary_desc": "No boundary for this test community",
                "verification_method": "None required here",
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: joining communities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_creates_registered_membership(
    db_session: AsyncSession, community: Community, regular_user: User
) -> None:
    async with _make_client(db_session, regular_user) as c:
        resp = await c.post(f"/api/v1/communities/{community.slug}/join")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["member_count"] == 1

    # Verify DB state
    result = await db_session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    membership = result.scalar_one()
    assert membership.tier == UserTier.REGISTERED
    assert membership.is_active is True


@pytest.mark.asyncio
async def test_double_join_is_idempotent(
    db_session: AsyncSession, community: Community, regular_user: User
) -> None:
    from sqlalchemy import select, func

    # Join once
    async with _make_client(db_session, regular_user) as c:
        await c.post(f"/api/v1/communities/{community.slug}/join")
    app.dependency_overrides.clear()

    # Join again — should be idempotent
    async with _make_client(db_session, regular_user) as c:
        resp = await c.post(f"/api/v1/communities/{community.slug}/join")
    app.dependency_overrides.clear()

    assert resp.status_code == 200

    # Exactly one membership row
    count_result = await db_session.execute(
        select(func.count()).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    assert count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_invite_only_community_blocks_join(
    db_session: AsyncSession, private_community: Community, regular_user: User
) -> None:
    async with _make_client(db_session, regular_user) as c:
        resp = await c.post(f"/api/v1/communities/{private_community.slug}/join")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: audit log scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_community_audit_returns_only_that_communitys_events(
    db_session: AsyncSession, community: Community, regular_user: User
) -> None:
    """Events with community_id=community.id appear in community audit; platform audit excluded."""
    from app.core.audit import log_event

    # Community-scoped event
    await log_event(
        db_session,
        event_type=AuditEventType.COMMUNITY_MEMBER_JOINED,
        target_type="community_membership",
        target_id=uuid.uuid4(),
        payload={},
        actor_id=regular_user.id,
        community_id=community.id,
    )
    # Platform-level event (no community)
    await log_event(
        db_session,
        event_type=AuditEventType.USER_REGISTERED,
        target_type="user",
        target_id=regular_user.id,
        payload={},
        actor_id=regular_user.id,
    )
    await db_session.commit()

    async with _make_client(db_session) as c:
        resp = await c.get(f"/api/v1/communities/{community.slug}/audit")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["event_type"] == "community_member_joined"


@pytest.mark.asyncio
async def test_platform_audit_returns_only_null_community_events(
    db_session: AsyncSession, community: Community, regular_user: User
) -> None:
    """GET /api/v1/audit returns only events where community_id IS NULL."""
    from app.core.audit import log_event

    # Platform-level event
    await log_event(
        db_session,
        event_type=AuditEventType.USER_REGISTERED,
        target_type="user",
        target_id=regular_user.id,
        payload={},
        actor_id=regular_user.id,
    )
    # Community-scoped event (should NOT appear in platform audit)
    await log_event(
        db_session,
        event_type=AuditEventType.COMMUNITY_MEMBER_JOINED,
        target_type="community_membership",
        target_id=uuid.uuid4(),
        payload={},
        actor_id=regular_user.id,
        community_id=community.id,
    )
    await db_session.commit()

    async with _make_client(db_session) as c:
        resp = await c.get("/api/v1/audit")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["event_type"] == "user_registered"


# ---------------------------------------------------------------------------
# Tests: facilitator request approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_community_admin_can_approve_facilitator_request(
    db_session: AsyncSession,
    community: Community,
    community_admin: User,
    regular_user: User,
) -> None:
    """Community admin approves → CommunityMembership.tier promoted to facilitator."""
    from sqlalchemy import select

    req = FacilitatorRequest(
        user_id=regular_user.id,
        community_id=community.id,
        reason="I want to help facilitate this community.",
    )
    db_session.add(req)
    await db_session.commit()

    async with _make_client(db_session, community_admin) as c:
        resp = await c.post(f"/api/v1/admin/facilitator-requests/{req.id}/approve")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"

    # CommunityMembership must now exist at facilitator tier
    result = await db_session.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    membership = result.scalar_one()
    assert membership.tier == UserTier.FACILITATOR


@pytest.mark.asyncio
async def test_platform_admin_can_approve_any_communitys_request(
    db_session: AsyncSession,
    community: Community,
    platform_admin: User,
    regular_user: User,
) -> None:
    from sqlalchemy import select

    req = FacilitatorRequest(
        user_id=regular_user.id,
        community_id=community.id,
        reason="Platform admin approving this community request.",
    )
    db_session.add(req)
    await db_session.commit()

    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(f"/api/v1/admin/facilitator-requests/{req.id}/approve")
    app.dependency_overrides.clear()

    assert resp.status_code == 200

    result = await db_session.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    membership = result.scalar_one()
    assert membership.tier == UserTier.FACILITATOR


@pytest.mark.asyncio
async def test_non_admin_cannot_approve_facilitator_request(
    db_session: AsyncSession,
    community: Community,
    regular_user: User,
) -> None:
    """A regular member (no admin tier in any community) gets 403 on approve."""
    req = FacilitatorRequest(
        user_id=regular_user.id,
        community_id=community.id,
        reason="Non-admin attempting to approve own request.",
    )
    db_session.add(req)
    await db_session.commit()

    # Use a different user with no admin privileges
    other_user = User(
        supabase_uid="uid-other",
        email="other@example.com",
        display_name="OtherUser",
        tier=UserTier.REGISTERED,
    )
    db_session.add(other_user)
    await db_session.commit()

    async with _make_client(db_session, other_user) as c:
        resp = await c.post(f"/api/v1/admin/facilitator-requests/{req.id}/approve")
    app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_creates_membership_if_not_exists(
    db_session: AsyncSession,
    community: Community,
    platform_admin: User,
    regular_user: User,
) -> None:
    """Approving a request for a non-member creates a new CommunityMembership at facilitator."""
    from sqlalchemy import select

    req = FacilitatorRequest(
        user_id=regular_user.id,
        community_id=community.id,
        reason="User was never a member — membership should be created on approval.",
    )
    db_session.add(req)
    await db_session.commit()

    # Confirm no existing membership
    existing = await db_session.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    assert existing.scalar_one_or_none() is None

    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(f"/api/v1/admin/facilitator-requests/{req.id}/approve")
    app.dependency_overrides.clear()

    assert resp.status_code == 200

    # Membership must now exist
    result = await db_session.execute(
        select(CommunityMembership).where(
            CommunityMembership.community_id == community.id,
            CommunityMembership.user_id == regular_user.id,
        )
    )
    membership = result.scalar_one()
    assert membership.tier == UserTier.FACILITATOR


# ---------------------------------------------------------------------------
# Tests: public community list and detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_community_list_accessible_without_auth(
    db_session: AsyncSession, community: Community
) -> None:
    async with _make_client(db_session) as c:
        resp = await c.get("/api/v1/communities")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    slugs = [c["slug"] for c in data]
    assert "redlands" in slugs


@pytest.mark.asyncio
async def test_private_community_hidden_from_unauthenticated(
    db_session: AsyncSession, private_community: Community
) -> None:
    async with _make_client(db_session) as c:
        resp = await c.get(f"/api/v1/communities/{private_community.slug}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_platform_admin_sees_private_community(
    db_session: AsyncSession, private_community: Community, platform_admin: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.get(f"/api/v1/communities/{private_community.slug}")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["slug"] == "private-group"
