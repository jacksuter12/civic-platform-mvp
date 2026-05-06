"""
Tests for proposal soft-delete.

Covers:
- Author can delete during PROPOSING → 204
- Non-author → 403
- Author during VOTING phase → 403
- Deleted proposal absent from GET /thread/{id} list
- GET /proposals/{id} on deleted → 404
- Audit log contains proposal_deleted with community_id
"""
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.main import app
from app.models.audit import AuditLog, AuditEventType
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
        slug="del-perms-community",
        name="Delete Perms Community",
        description="Community for proposal delete permission tests.",
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
async def domain(db_session: AsyncSession, community: Community) -> Domain:
    d = Domain(
        community_id=community.id,
        slug="del-perms-domain",
        name="Delete Perms Domain",
        description="Test domain for delete perms.",
    )
    db_session.add(d)
    await db_session.commit()
    return d


@pytest_asyncio.fixture
async def author(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-del-author",
        email="del-author@example.com",
        display_name="DelAuthor",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=UserTier.REGISTERED,
        joined_at=datetime.now(UTC),
    ))
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def non_author(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-del-nonauthor",
        email="del-nonauthor@example.com",
        display_name="NonAuthor",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=UserTier.REGISTERED,
        joined_at=datetime.now(UTC),
    ))
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def thread_proposing(
    db_session: AsyncSession, domain: Domain, community: Community, author: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=author.id,
        title="Thread for delete-permission tests",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def thread_voting(
    db_session: AsyncSession, domain: Domain, community: Community, author: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=author.id,
        title="Thread in voting (delete blocked)",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.VOTING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def proposal(
    db_session: AsyncSession, thread_proposing: Thread, author: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_proposing.id,
        created_by_id=author.id,
        title="Proposal to be deleted",
        description="This proposal will be soft-deleted in tests.",
        body_html="<p>Body</p>",
        status=ProposalStatus.SUBMITTED,
        current_version_number=1,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def proposal_in_voting_thread(
    db_session: AsyncSession, thread_voting: Thread, author: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_voting.id,
        created_by_id=author.id,
        title="Proposal in voting thread",
        description="Cannot delete during VOTING phase.",
        body_html="<p>Body</p>",
        status=ProposalStatus.SUBMITTED,
        current_version_number=1,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_can_delete_during_proposing(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    author: User,
    thread_proposing: Thread,
):
    """Author deletes their own proposal in PROPOSING phase → 204."""
    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_optional_user] = lambda: author
    try:
        resp = await client.delete(f"/api/v1/proposals/{proposal.id}")
        assert resp.status_code == 204

        # Verify DB row has deleted_at set
        await db_session.refresh(proposal)
        assert proposal.deleted_at is not None
        assert proposal.deleted_by_id == author.id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_author_cannot_delete(
    client: AsyncClient,
    proposal: Proposal,
    non_author: User,
):
    """Non-author → 403."""
    app.dependency_overrides[get_current_user] = lambda: non_author
    app.dependency_overrides[get_optional_user] = lambda: non_author
    try:
        resp = await client.delete(f"/api/v1/proposals/{proposal.id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_author_cannot_delete_in_voting_phase(
    client: AsyncClient,
    proposal_in_voting_thread: Proposal,
    author: User,
):
    """Author cannot delete during VOTING phase → 403."""
    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_optional_user] = lambda: author
    try:
        resp = await client.delete(f"/api/v1/proposals/{proposal_in_voting_thread.id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_deleted_proposal_absent_from_list(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    author: User,
    thread_proposing: Thread,
):
    """After deletion, proposal does not appear in thread list."""
    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_optional_user] = lambda: author
    try:
        # Soft-delete
        del_resp = await client.delete(f"/api/v1/proposals/{proposal.id}")
        assert del_resp.status_code == 204

        # List should be empty
        list_resp = await client.get(f"/api/v1/proposals/thread/{thread_proposing.id}")
        assert list_resp.status_code == 200
        ids = [p["id"] for p in list_resp.json()]
        assert str(proposal.id) not in ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_deleted_proposal_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    author: User,
):
    """GET on a deleted proposal returns 404."""
    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_optional_user] = lambda: author
    try:
        await client.delete(f"/api/v1/proposals/{proposal.id}")
        get_resp = await client.get(f"/api/v1/proposals/{proposal.id}")
        assert get_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_writes_audit_log_with_community_id(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    author: User,
    community: Community,
    thread_proposing: Thread,
):
    """Deletion records PROPOSAL_DELETED audit event scoped to community."""
    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_optional_user] = lambda: author
    try:
        resp = await client.delete(f"/api/v1/proposals/{proposal.id}")
        assert resp.status_code == 204

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEventType.PROPOSAL_DELETED,
                AuditLog.target_id == proposal.id,
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.community_id == community.id
        assert log.actor_id == author.id
        assert log.payload["title"] == proposal.title
    finally:
        app.dependency_overrides.clear()
