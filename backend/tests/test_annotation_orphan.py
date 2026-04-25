"""
Tests for annotation mark-orphaned endpoint.

Validates:
- Registered member can mark a proposal annotation as orphaned
- mark-orphaned is idempotent (200 on second call, orphaned_at unchanged)
- orphaned_at is set after first call
- ANNOTATION_ORPHANED audit event is written with community_id
- target_type != 'proposal' returns 400
- Deleted annotation returns 404
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.main import app
from app.models.annotation import Annotation
from app.models.audit import AuditEventType, AuditLog
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.proposal import Proposal, ProposalStatus
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="orphan-community",
        name="Orphan Test Community",
        description="Community for orphan tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Test boundary",
        verification_method="Self-verify",
        is_public=True,
        is_invite_only=False,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def domain(db_session: AsyncSession, community: Community) -> Domain:
    d = Domain(
        community_id=community.id,
        slug="orphan-domain",
        name="Orphan Domain",
        description="Test domain",
    )
    db_session.add(d)
    await db_session.commit()
    return d


async def _make_member(
    db_session: AsyncSession,
    community: Community,
    uid: str,
    email: str,
    name: str,
    tier: UserTier = UserTier.REGISTERED,
) -> User:
    u = User(supabase_uid=uid, email=email, display_name=name, tier=tier)
    db_session.add(u)
    await db_session.flush()
    db_session.add(CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=tier,
        joined_at=datetime.now(UTC),
    ))
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def member(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(db_session, community, "uid-orphan-mem", "orphan-mem@example.com", "Member")
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def thread(
    db_session: AsyncSession, community: Community, domain: Domain, member: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=member.id,
        title="Orphan test thread",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def proposal(db_session: AsyncSession, thread: Thread, member: User) -> Proposal:
    p = Proposal(
        thread_id=thread.id,
        created_by_id=member.id,
        title="Orphan proposal for community use",
        description="A proposal about something in the community center area for residents to enjoy.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def annotation(db_session: AsyncSession, proposal: Proposal, member: User) -> Annotation:
    a = Annotation(
        target_type="proposal",
        target_id=str(proposal.id),
        anchor_data={"selector": [{"type": "TextQuoteSelector", "exact": "community center"}]},
        author_id=member.id,
        body="This anchor will become orphaned.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


@pytest_asyncio.fixture
async def wiki_annotation(db_session: AsyncSession, member: User) -> Annotation:
    a = Annotation(
        target_type="wiki",
        target_id="test-wiki-slug",
        anchor_data={"type": "section", "section_id": "intro"},
        author_id=member.id,
        body="Wiki annotation.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_orphaned_sets_orphaned_at(
    client: AsyncClient,
    annotation: Annotation,
    member: User,
    db_session: AsyncSession,
) -> None:
    """mark-orphaned sets orphaned_at on the annotation."""
    app.dependency_overrides[get_current_user] = lambda: member
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["orphaned_at"] is not None

    # Verify in DB
    await db_session.refresh(annotation)
    assert annotation.orphaned_at is not None


@pytest.mark.asyncio
async def test_mark_orphaned_is_idempotent(
    client: AsyncClient,
    annotation: Annotation,
    member: User,
) -> None:
    """Calling mark-orphaned twice returns 200 both times; orphaned_at is stable."""
    app.dependency_overrides[get_current_user] = lambda: member

    resp1 = await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")
    assert resp1.status_code == 200
    first_orphaned_at = resp1.json()["orphaned_at"]

    resp2 = await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")
    assert resp2.status_code == 200
    second_orphaned_at = resp2.json()["orphaned_at"]

    assert first_orphaned_at == second_orphaned_at


@pytest.mark.asyncio
async def test_mark_orphaned_writes_audit_event(
    client: AsyncClient,
    annotation: Annotation,
    member: User,
    db_session: AsyncSession,
) -> None:
    """mark-orphaned writes ANNOTATION_ORPHANED to the audit log with community_id."""
    app.dependency_overrides[get_current_user] = lambda: member
    await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_ORPHANED,
            AuditLog.target_id == annotation.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.community_id is not None


@pytest.mark.asyncio
async def test_mark_orphaned_idempotent_no_double_audit(
    client: AsyncClient,
    annotation: Annotation,
    member: User,
    db_session: AsyncSession,
) -> None:
    """Second call to mark-orphaned does not write a second audit event."""
    app.dependency_overrides[get_current_user] = lambda: member
    await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")
    await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_ORPHANED,
            AuditLog.target_id == annotation.id,
        )
    )
    logs = list(result.scalars())
    assert len(logs) == 1, "Should only write one ANNOTATION_ORPHANED event"


@pytest.mark.asyncio
async def test_wiki_annotation_cannot_be_orphaned(
    client: AsyncClient,
    wiki_annotation: Annotation,
    member: User,
) -> None:
    """mark-orphaned on a wiki annotation returns 400."""
    app.dependency_overrides[get_current_user] = lambda: member
    resp = await client.post(f"/api/v1/annotations/{wiki_annotation.id}/mark-orphaned")
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_mark_orphaned_on_deleted_annotation_returns_404(
    client: AsyncClient,
    annotation: Annotation,
    member: User,
    db_session: AsyncSession,
) -> None:
    """mark-orphaned on a soft-deleted annotation returns 404."""
    annotation.deleted_at = datetime.now(UTC)
    annotation.body = "[deleted]"
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: member
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/mark-orphaned")
    assert resp.status_code == 404, resp.text
