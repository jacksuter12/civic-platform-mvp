"""
Tests for thread lifecycle: create → advance phase → proposals → votes.
These tests validate deliberative rules, not just CRUD.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


@pytest.fixture
async def domain(db_session: AsyncSession) -> Domain:
    d = Domain(slug="healthcare", name="Healthcare", description="Test domain")
    db_session.add(d)
    await db_session.commit()
    return d


@pytest.fixture
async def participant(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-participant",
        email="participant@example.com",
        display_name="Alice",
        tier=UserTier.PARTICIPANT,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def facilitator(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-facilitator",
        email="facilitator@example.com",
        display_name="Bob",
        tier=UserTier.FACILITATOR,
    )
    db_session.add(u)
    await db_session.commit()
    return u


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

    # Thread in OPEN — cannot advance to VOTING (must go OPEN→DELIBERATING→...)
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
    assert not thread.can_advance_to(ThreadStatus.OPEN)  # no going back


@pytest.mark.asyncio
async def test_audit_log_populated_on_thread_creation(
    db_session: AsyncSession, domain: Domain, participant: User
) -> None:
    from app.core.audit import log_event
    from app.models.audit import AuditEventType, AuditLog
    from sqlalchemy import select

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
