"""
Tests for annotation feature/unfeature endpoints.

Validates:
- Facilitator can feature a proposal annotation → 200, featured_at set
- Facilitator can unfeature → 200, featured_at cleared
- Non-facilitator (registered member) returns 403
- target_type='wiki' returns 400
- Double-feature returns 409
- Unfeature when not featured returns 409
- Audit events ANNOTATION_FEATURED and ANNOTATION_UNFEATURED written
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
        slug="feature-community",
        name="Feature Test Community",
        description="Community for feature tests.",
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
        slug="feature-domain",
        name="Feature Domain",
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
async def proposal_author(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(db_session, community, "uid-feat-author", "feat-author@example.com", "PropAuthor")
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def facilitator(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(
        db_session, community,
        "uid-feat-fac", "feat-fac@example.com", "Facilitator",
        tier=UserTier.FACILITATOR,
    )
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def registered_member(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(
        db_session, community,
        "uid-feat-reg", "feat-reg@example.com", "Registered",
    )
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def thread(
    db_session: AsyncSession, community: Community, domain: Domain, proposal_author: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=proposal_author.id,
        title="Feature test thread",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def proposal(
    db_session: AsyncSession, thread: Thread, proposal_author: User
) -> Proposal:
    p = Proposal(
        thread_id=thread.id,
        created_by_id=proposal_author.id,
        title="Feature proposal for community garden",
        description="We should build a new community garden in the park near the town center.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def annotation(
    db_session: AsyncSession, proposal: Proposal, registered_member: User
) -> Annotation:
    a = Annotation(
        target_type="proposal",
        target_id=str(proposal.id),
        anchor_data={"selector": [{"type": "TextQuoteSelector", "exact": "community garden"}]},
        author_id=registered_member.id,
        body="This needs more detail.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


@pytest_asyncio.fixture
async def wiki_annotation(db_session: AsyncSession, facilitator: User) -> Annotation:
    a = Annotation(
        target_type="wiki",
        target_id="some-wiki-slug",
        anchor_data={"type": "section", "section_id": "intro"},
        author_id=facilitator.id,
        body="Wiki annotation.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facilitator_can_feature(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
    db_session: AsyncSession,
) -> None:
    """Facilitator can feature a proposal annotation."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["featured_at"] is not None
    assert data["featured_by_id"] == str(facilitator.id)


@pytest.mark.asyncio
async def test_facilitator_can_unfeature(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
) -> None:
    """Facilitator can unfeature a featured annotation."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/unfeature")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["featured_at"] is None
    assert data["featured_by_id"] is None


@pytest.mark.asyncio
async def test_registered_member_cannot_feature(
    client: AsyncClient,
    annotation: Annotation,
    registered_member: User,
) -> None:
    """Registered member gets 403 on feature."""
    app.dependency_overrides[get_current_user] = lambda: registered_member
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_wiki_annotation_cannot_be_featured(
    client: AsyncClient,
    wiki_annotation: Annotation,
    facilitator: User,
) -> None:
    """Featuring a wiki annotation returns 400."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    resp = await client.post(f"/api/v1/annotations/{wiki_annotation.id}/feature")
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_double_feature_returns_409(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
) -> None:
    """Featuring an already-featured annotation returns 409."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_unfeature_when_not_featured_returns_409(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
) -> None:
    """Unfeature on an annotation that is not featured returns 409."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    resp = await client.post(f"/api/v1/annotations/{annotation.id}/unfeature")
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_feature_writes_audit_event(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
    db_session: AsyncSession,
) -> None:
    """Featuring an annotation writes ANNOTATION_FEATURED to the audit log."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    await client.post(f"/api/v1/annotations/{annotation.id}/feature")

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_FEATURED,
            AuditLog.target_id == annotation.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.community_id is not None


@pytest.mark.asyncio
async def test_unfeature_writes_audit_event(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
    db_session: AsyncSession,
) -> None:
    """Unfeature writes ANNOTATION_UNFEATURED to the audit log."""
    app.dependency_overrides[get_current_user] = lambda: facilitator
    await client.post(f"/api/v1/annotations/{annotation.id}/feature")
    await client.post(f"/api/v1/annotations/{annotation.id}/unfeature")

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_UNFEATURED,
            AuditLog.target_id == annotation.id,
        )
    )
    log = result.scalar_one_or_none()
    assert log is not None
