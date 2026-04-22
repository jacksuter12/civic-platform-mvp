"""
Tests for thread lifecycle: create → advance phase → proposals → votes.
These tests validate deliberative rules, not just CRUD.

Session 3 additions:
- community + membership fixtures for all user fixtures.
- Cross-community facilitator test: a facilitator in community A cannot
  advance a thread that belongs to community B (403).
"""

import uuid
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.thread import Thread, ThreadStatus
from app.models.user import PlatformRole, User, UserTier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="test-community",
        name="Test Community",
        description="Community for thread tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Test boundary",
        verification_method="Test verification",
        is_public=True,
        is_invite_only=False,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def community_b(db_session: AsyncSession) -> Community:
    c = Community(
        slug="community-b",
        name="Community B",
        description="A second community for cross-community tests.",
        community_type=CommunityType.ORGANIZATIONAL,
        boundary_desc="B boundary",
        verification_method="B verification",
        is_public=True,
        is_invite_only=False,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest.fixture
async def domain(db_session: AsyncSession, community: Community) -> Domain:
    d = Domain(
        community_id=community.id,
        slug="healthcare",
        name="Healthcare",
        description="Test domain",
    )
    db_session.add(d)
    await db_session.commit()
    return d


@pytest_asyncio.fixture
async def participant(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-participant",
        email="participant@example.com",
        display_name="Alice",
        tier=UserTier.PARTICIPANT,
    )
    db_session.add(u)
    await db_session.flush()

    membership = CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=UserTier.REGISTERED,
        joined_at=datetime.now(UTC),
    )
    db_session.add(membership)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def facilitator(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-facilitator",
        email="facilitator@example.com",
        display_name="Bob",
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
# Helpers
# ---------------------------------------------------------------------------


def _make_client(db_session: AsyncSession, user: User | None = None):
    """Override auth and DB so tests don't need real JWTs."""

    async def override_db():
        yield db_session

    async def override_required_user():
        if user is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    async def override_optional_user():
        return user

    overrides = {
        get_db: override_db,
        get_optional_user: override_optional_user,
    }
    if user is not None:
        overrides[get_current_user] = override_required_user

    app.dependency_overrides.update(overrides)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Model-layer tests (bypass routes — community_id not required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_phase_gate_enforcement(
    db_session: AsyncSession, domain: Domain, participant: User
) -> None:
    """Proposals cannot be submitted while thread is OPEN."""
    thread = Thread(
        domain_id=domain.id,
        created_by_id=participant.id,
        title="Should we fund community clinics?",
        prompt="What should our approach to funding be?",
        status=ThreadStatus.OPEN,
    )
    db_session.add(thread)
    await db_session.commit()

    assert not thread.can_advance_to(ThreadStatus.VOTING)
    assert thread.can_advance_to(ThreadStatus.DELIBERATING)


@pytest.mark.asyncio
async def test_thread_full_lifecycle(db_session: AsyncSession, domain: Domain) -> None:
    """Thread follows the strict state machine: OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED."""
    thread = Thread(
        domain_id=domain.id,
        created_by_id=uuid.uuid4(),
        title="Test thread",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.OPEN,
    )
    db_session.add(thread)
    await db_session.commit()

    for expected_next in [
        ThreadStatus.DELIBERATING,
        ThreadStatus.PROPOSING,
        ThreadStatus.VOTING,
        ThreadStatus.CLOSED,
    ]:
        assert thread.can_advance_to(expected_next)
        thread.status = expected_next
        await db_session.commit()

    assert thread.status == ThreadStatus.CLOSED
    assert not thread.can_advance_to(ThreadStatus.OPEN)


@pytest.mark.asyncio
async def test_audit_log_populated_on_thread_creation(
    db_session: AsyncSession, domain: Domain, participant: User
) -> None:
    from app.core.audit import log_event
    from app.models.audit import AuditEventType, AuditLog

    thread = Thread(
        domain_id=domain.id,
        created_by_id=participant.id,
        title="Audit test thread",
        prompt="This is a test deliberation prompt with sufficient length.",
    )
    db_session.add(thread)
    await db_session.flush()

    await log_event(
        db_session,
        event_type=AuditEventType.THREAD_CREATED,
        target_type="thread",
        target_id=thread.id,
        payload={"title": thread.title},
        actor_id=participant.id,
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.target_id == thread.id)
    )
    log_entry = result.scalar_one()
    assert log_entry.event_type == AuditEventType.THREAD_CREATED
    assert log_entry.actor_id == participant.id
    assert log_entry.payload["title"] == "Audit test thread"


# ---------------------------------------------------------------------------
# HTTP-layer test: cross-community facilitator cannot advance phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_community_facilitator_cannot_advance_phase(
    db_session: AsyncSession,
    community: Community,
    community_b: Community,
    domain: Domain,
    facilitator: User,
) -> None:
    """
    A facilitator in community A must receive 403 when attempting to advance
    the phase of a thread that belongs to community B.
    """
    # facilitator has FACILITATOR membership in community (A) but NOT in community_b (B)
    # Create a thread in community_b
    thread = Thread(
        community_id=community_b.id,
        domain_id=domain.id,
        created_by_id=facilitator.id,
        title="Thread in community B",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.OPEN,
    )
    db_session.add(thread)
    await db_session.commit()

    async with _make_client(db_session, facilitator) as c:
        resp = await c.patch(
            f"/api/v1/threads/{thread.id}/advance",
            json={
                "target_status": "deliberating",
                "reason": "Moving to deliberation phase now.",
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Expected 403, got {resp.status_code}: {resp.text}"
    )
