"""
Tests for the Community.research_mode flag.

research_mode marks a synthetic-participant research space. Orchestration
scripts (scripts/llm_panel/) may post on behalf of bot users in such a
community. Real communities never set it.

Rules validated here:
  - Defaults to False on both the model and the create API.
  - Settable at creation by a platform admin.
  - NOT mutable via PATCH /communities/{slug} — the flag is creation-only.
  - Excluded from GET /communities for everyone, platform admins included.
  - Still readable by slug via GET /communities/{slug}.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.community import Community, CommunityType
from app.models.user import PlatformRole, User, UserTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def platform_admin(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-research-admin",
        email="research-admin@example.com",
        display_name="ResearchAdmin",
        tier=UserTier.ADMIN,
        platform_role=PlatformRole.PLATFORM_ADMIN,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-research-regular",
        email="research-regular@example.com",
        display_name="ResearchRegular",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def normal_community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="ordinary-town",
        name="Ordinary Town",
        description="A perfectly ordinary community of humans.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Ordinary Town municipal boundary",
        verification_method="Email domain verification",
        is_public=True,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def research_community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="research-llm-panel",
        name="LLM Panel Research Space",
        description="Synthetic-participant research space for the LLM panel.",
        community_type=CommunityType.TECHNICAL,
        boundary_desc="Synthetic participants seeded by the panel scripts",
        verification_method="Seeded bot accounts only",
        is_public=True,
        is_invite_only=True,
        research_mode=True,
    )
    db_session.add(c)
    await db_session.commit()
    return c


def _make_client(db_session: AsyncSession, user: User | None = None):
    async def override_db():
        yield db_session

    async def override_required_user():
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    async def override_optional_user():
        return user

    overrides: dict = {
        get_db: override_db,
        get_optional_user: override_optional_user,
    }
    if user is not None:
        overrides[get_current_user] = override_required_user

    app.dependency_overrides.update(overrides)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_mode_defaults_to_false_on_model(
    db_session: AsyncSession, normal_community: Community
) -> None:
    """A community created without the flag is not a research space."""
    assert normal_community.research_mode is False


@pytest.mark.asyncio
async def test_research_mode_defaults_to_false_via_api(
    db_session: AsyncSession, platform_admin: User
) -> None:
    """Omitting research_mode from the create payload leaves it False."""
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(
            "/api/v1/communities",
            json={
                "slug": "default-flag-town",
                "name": "Default Flag Town",
                "description": "Created without mentioning research_mode at all.",
                "community_type": "geographic",
                "boundary_desc": "Default Flag Town municipal boundary",
                "verification_method": "Email domain verification",
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 201
    assert resp.json()["research_mode"] is False

    result = await db_session.execute(
        select(Community).where(Community.slug == "default-flag-town")
    )
    assert result.scalar_one().research_mode is False


# ---------------------------------------------------------------------------
# Settable at creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_can_create_research_mode_community(
    db_session: AsyncSession, platform_admin: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(
            "/api/v1/communities",
            json={
                "slug": "llm-panel-space",
                "name": "LLM Panel Space",
                "description": "Synthetic-participant research space for the panel.",
                "community_type": "technical",
                "boundary_desc": "Synthetic participants seeded by panel scripts",
                "verification_method": "Seeded bot accounts only",
                "is_invite_only": True,
                "research_mode": True,
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 201
    assert resp.json()["research_mode"] is True

    result = await db_session.execute(
        select(Community).where(Community.slug == "llm-panel-space")
    )
    assert result.scalar_one().research_mode is True


# ---------------------------------------------------------------------------
# Not mutable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_mode_not_settable_via_patch(
    db_session: AsyncSession, platform_admin: User, normal_community: Community
) -> None:
    """
    CommunityUpdate has no research_mode field, so pydantic drops it from the
    payload and the community stays non-research.
    """
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.patch(
            f"/api/v1/communities/{normal_community.slug}",
            json={"research_mode": True},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["research_mode"] is False

    await db_session.refresh(normal_community)
    assert normal_community.research_mode is False


@pytest.mark.asyncio
async def test_research_mode_not_clearable_via_patch(
    db_session: AsyncSession, platform_admin: User, research_community: Community
) -> None:
    """The flag is creation-only in both directions — it cannot be turned off."""
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.patch(
            f"/api/v1/communities/{research_community.slug}",
            json={"research_mode": False, "name": "Renamed Research Space"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["research_mode"] is True

    await db_session.refresh(research_community)
    assert research_community.research_mode is True


# ---------------------------------------------------------------------------
# Directory exclusion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_community_excluded_from_directory_unauthenticated(
    db_session: AsyncSession,
    normal_community: Community,
    research_community: Community,
) -> None:
    async with _make_client(db_session) as c:
        resp = await c.get("/api/v1/communities")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    slugs = [item["slug"] for item in resp.json()]
    assert "ordinary-town" in slugs
    assert "research-llm-panel" not in slugs


@pytest.mark.asyncio
async def test_research_community_excluded_from_directory_for_platform_admin(
    db_session: AsyncSession,
    platform_admin: User,
    normal_community: Community,
    research_community: Community,
) -> None:
    """Platform admins see private communities, but never research ones."""
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.get("/api/v1/communities")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    slugs = [item["slug"] for item in resp.json()]
    assert "ordinary-town" in slugs
    assert "research-llm-panel" not in slugs


@pytest.mark.asyncio
async def test_research_community_still_readable_by_slug(
    db_session: AsyncSession, research_community: Community, regular_user: User
) -> None:
    """
    Excluded from the directory, not hidden. The seeded bots read the
    community they post in, so a public research community must stay
    reachable at its slug.
    """
    async with _make_client(db_session, regular_user) as c:
        resp = await c.get(f"/api/v1/communities/{research_community.slug}")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "research-llm-panel"
    assert body["research_mode"] is True
