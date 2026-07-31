"""
Tests for User.is_synthetic — the bot label.

The point of the flag is that a human always knows whether they are reading a
person. So the tests care about two things: that only an accountable actor can
set it, and that it actually reaches every surface where a name is rendered.

Rules validated here:
  - Defaults to False; not settable at registration (the route is unauthenticated,
    so a self-asserted label would be worth nothing).
  - Platform admin can set and clear it; a regular user cannot.
  - Setting it writes an audit event naming the admin who did it.
  - Idempotent — re-setting the same value writes no second audit entry.
  - Surfaces on the member list, the add-member search, post author bylines,
    the admin user list, and /auth/me.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.audit import AuditEventType, AuditLog
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.post import Post
from app.models.thread import Thread, ThreadStatus
from app.models.user import PlatformRole, User, UserTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def platform_admin(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-synth-admin",
        email="synth-admin@example.com",
        display_name="SynthAdmin",
        tier=UserTier.ADMIN,
        platform_role=PlatformRole.PLATFORM_ADMIN,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def human(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-synth-human",
        email="human@example.com",
        display_name="RealPerson",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def bot(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="llm-panel-a-claude-panel",
        email="a-claude-panel@llm-panel.example",
        display_name="Claude Panel",
        tier=UserTier.REGISTERED,
        is_synthetic=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="synth-town",
        name="Synth Town",
        description="A community used for synthetic-account labelling tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Synth Town municipal boundary",
        verification_method="Email domain verification",
        is_public=True,
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
# Default and self-assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_defaults_to_false(db_session: AsyncSession, human: User) -> None:
    assert human.is_synthetic is False


@pytest.mark.asyncio
async def test_registration_cannot_self_assert_the_label(
    db_session: AsyncSession,
) -> None:
    """
    POST /auth/register is unauthenticated. A label anyone could set on
    themselves would mean nothing, so UserCreate has no is_synthetic field and
    the value is ignored.
    """
    async with _make_client(db_session) as c:
        resp = await c.post(
            "/api/v1/auth/register",
            json={
                "supabase_uid": "uid-self-asserted",
                "email": "sneaky@example.com",
                "display_name": "Totally Human",
                "is_synthetic": True,
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 201
    assert resp.json()["is_synthetic"] is False

    result = await db_session.execute(
        select(User).where(User.supabase_uid == "uid-self-asserted")
    )
    assert result.scalar_one().is_synthetic is False


# ---------------------------------------------------------------------------
# Who can set it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_can_mark_and_unmark(
    db_session: AsyncSession, platform_admin: User, human: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        marked = await c.post(
            "/api/v1/admin/users/synthetic",
            json={"email": human.email, "is_synthetic": True, "reason": "test bot"},
        )
    app.dependency_overrides.clear()
    assert marked.status_code == 200
    assert marked.json()["is_synthetic"] is True
    await db_session.refresh(human)
    assert human.is_synthetic is True

    async with _make_client(db_session, platform_admin) as c:
        cleared = await c.post(
            "/api/v1/admin/users/synthetic",
            json={"email": human.email, "is_synthetic": False},
        )
    app.dependency_overrides.clear()
    assert cleared.status_code == 200
    assert cleared.json()["is_synthetic"] is False
    await db_session.refresh(human)
    assert human.is_synthetic is False


@pytest.mark.asyncio
async def test_regular_user_cannot_mark_anyone(
    db_session: AsyncSession, human: User
) -> None:
    async with _make_client(db_session, human) as c:
        resp = await c.post(
            "/api/v1/admin/users/synthetic",
            json={"email": human.email, "is_synthetic": True},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unknown_email_is_404(
    db_session: AsyncSession, platform_admin: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.post(
            "/api/v1/admin/users/synthetic",
            json={"email": "nobody@example.com", "is_synthetic": True},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marking_writes_an_audit_event_naming_the_admin(
    db_session: AsyncSession, platform_admin: User, human: User
) -> None:
    """The label is only worth something if you can see who applied it."""
    async with _make_client(db_session, platform_admin) as c:
        await c.post(
            "/api/v1/admin/users/synthetic",
            json={"email": human.email, "is_synthetic": True, "reason": "panel bot"},
        )
    app.dependency_overrides.clear()

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.USER_MARKED_SYNTHETIC,
            AuditLog.target_id == human.id,
        )
    )
    entry = result.scalar_one()
    assert entry.actor_id == platform_admin.id
    assert entry.payload == {"reason": "panel bot"}
    # Platform-level event — not scoped to any community.
    assert entry.community_id is None


@pytest.mark.asyncio
async def test_setting_the_same_value_twice_writes_one_audit_entry(
    db_session: AsyncSession, platform_admin: User, human: User
) -> None:
    for _ in range(3):
        async with _make_client(db_session, platform_admin) as c:
            resp = await c.post(
                "/api/v1/admin/users/synthetic",
                json={"email": human.email, "is_synthetic": True},
            )
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["is_synthetic"] is True

    count = await db_session.execute(
        select(func.count()).where(
            AuditLog.event_type == AuditEventType.USER_MARKED_SYNTHETIC,
            AuditLog.target_id == human.id,
        )
    )
    assert count.scalar_one() == 1


# ---------------------------------------------------------------------------
# Where humans actually see it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_label_appears_in_the_public_member_list(
    db_session: AsyncSession, community: Community, bot: User, human: User
) -> None:
    for user in (bot, human):
        db_session.add(
            CommunityMembership(
                community_id=community.id,
                user_id=user.id,
                tier=UserTier.REGISTERED,
                joined_at=datetime.now(UTC),
            )
        )
    await db_session.commit()

    async with _make_client(db_session) as c:
        resp = await c.get(f"/api/v1/communities/{community.slug}/members")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    by_name = {m["display_name"]: m["is_synthetic"] for m in resp.json()}
    assert by_name == {"Claude Panel": True, "RealPerson": False}


@pytest.mark.asyncio
async def test_label_appears_in_the_add_member_search(
    db_session: AsyncSession, community: Community, platform_admin: User, bot: User
) -> None:
    """
    This search covers every user on the platform, not just this community's
    members — so a facilitator adding people is exactly who needs the warning.
    """
    async with _make_client(db_session, platform_admin) as c:
        resp = await c.get(
            f"/api/v1/communities/{community.slug}/users/search", params={"q": "Claude"}
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["display_name"] == "Claude Panel"
    assert results[0]["is_synthetic"] is True


@pytest.mark.asyncio
async def test_label_appears_on_post_author_bylines(
    db_session: AsyncSession, community: Community, bot: User
) -> None:
    """Every byline on the platform is a UserPublic, so this covers all of them."""
    from app.models.domain import Domain

    domain = Domain(
        community_id=community.id,
        slug="general",
        name="General",
        description="General discussion",
    )
    db_session.add(domain)
    await db_session.flush()

    thread = Thread(
        community_id=community.id,
        domain_id=domain.id,
        title="A thread with a bot in it",
        prompt="Long enough prompt to satisfy the server-side validation limits.",
        status=ThreadStatus.DELIBERATING,
        created_by_id=bot.id,
    )
    db_session.add(thread)
    await db_session.flush()

    db_session.add(
        Post(
            thread_id=thread.id,
            author_id=bot.id,
            body="A contribution from a synthetic participant.",
        )
    )
    db_session.add(
        CommunityMembership(
            community_id=community.id,
            user_id=bot.id,
            tier=UserTier.REGISTERED,
            joined_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    async with _make_client(db_session, bot) as c:
        resp = await c.get(f"/api/v1/posts/thread/{thread.id}/flat")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    posts = resp.json()
    assert len(posts) == 1
    assert posts[0]["author"]["display_name"] == "Claude Panel"
    assert posts[0]["author"]["is_synthetic"] is True


@pytest.mark.asyncio
async def test_label_appears_in_the_admin_user_list_and_on_me(
    db_session: AsyncSession, platform_admin: User, bot: User
) -> None:
    async with _make_client(db_session, platform_admin) as c:
        listing = await c.get("/api/v1/admin/users")
    app.dependency_overrides.clear()
    assert listing.status_code == 200
    by_name = {u["display_name"]: u["is_synthetic"] for u in listing.json()}
    assert by_name["Claude Panel"] is True
    assert by_name["SynthAdmin"] is False

    async with _make_client(db_session, bot) as c:
        me = await c.get("/api/v1/auth/me")
    app.dependency_overrides.clear()
    assert me.status_code == 200
    assert me.json()["is_synthetic"] is True
