"""
Tests for proposal edit permission gates and Track Changes field correctness.

Focuses on the HTTP-layer behaviors updated in Session 04.A:
- require_can_edit_proposal: author-only, PROPOSING phase only
- parent_version_id is chained on each edit
- decision_reason = edit_summary
- can_edit is populated on ProposalDetail
- Audit log includes version_id
"""
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.main import app
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.proposal import Proposal, ProposalStatus
from app.models.proposal_version import ProposalVersion, ProposalVersionStatus
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="edit-perms-community",
        name="Edit Perms Community",
        description="Community for proposal edit permission tests.",
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
        slug="edit-perms-domain",
        name="Edit Perms Domain",
        description="Test domain for edit perms.",
    )
    db_session.add(d)
    await db_session.commit()
    return d


@pytest_asyncio.fixture
async def author(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-edit-author",
        email="edit-author@example.com",
        display_name="EditAuthor",
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
        supabase_uid="uid-edit-nonauthor",
        email="edit-nonauthor@example.com",
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
        title="Thread for edit-permission tests",
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
        title="Thread in voting (edit blocked)",
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
        title="Original proposal title",
        description="Original proposal description with enough length to be valid here.",
        body_html="<p>Original</p>",
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
        description="Proposal in a thread that is past PROPOSING phase.",
        body_html="<p>Voting phase</p>",
        status=ProposalStatus.VOTING,
        current_version_number=1,
    )
    db_session.add(p)
    await db_session.commit()
    return p


def _auth(user: User):
    def _dep():
        return user
    return _dep


# ---------------------------------------------------------------------------
# Permission gate tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_can_edit_during_proposing(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
) -> None:
    """Author can PATCH their own proposal when thread is PROPOSING."""
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Updated proposal title (author)",
                "description": "Updated description with enough length to pass validation here.",
                "edit_summary": "Clarified the proposal scope after feedback.",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["title"] == "Updated proposal title (author)"
        assert "body_html" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_non_author_cannot_edit(
    client: AsyncClient,
    proposal: Proposal,
    non_author: User,
) -> None:
    """Non-author receives 403 even during PROPOSING phase."""
    app.dependency_overrides[get_current_user] = _auth(non_author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Non-author attempt to edit",
                "description": "Should be rejected because this user is not the author.",
                "edit_summary": "Unauthorized edit attempt.",
            },
        )
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_author_cannot_edit_during_voting(
    client: AsyncClient,
    proposal_in_voting_thread: Proposal,
    author: User,
) -> None:
    """Author receives 403 when thread has advanced past PROPOSING."""
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal_in_voting_thread.id}",
            json={
                "title": "Author edit attempt during voting",
                "description": "Should be blocked because thread is in VOTING phase.",
                "edit_summary": "Trying to edit during voting.",
            },
        )
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_edit_summary_too_short_returns_422(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
) -> None:
    """edit_summary under 10 chars is rejected by schema validation."""
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Valid title (ten chars)",
                "description": "Valid description with enough length to pass the validation check.",
                "edit_summary": "short",  # < 10 chars
            },
        )
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_edit_summary_missing_returns_422(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
) -> None:
    """Missing edit_summary is rejected by schema validation."""
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Valid title (ten chars)",
                "description": "Valid description with enough length to pass the validation check.",
                # edit_summary omitted
            },
        )
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Track Changes correctness (Session 04.A fixes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_edit_creates_version_with_none_parent(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
    db_session: AsyncSession,
) -> None:
    """
    First edit: parent_version_id is None (no prior version exists).
    decision_reason equals the edit_summary.
    """
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "First edit title",
                "description": "First edit description with enough length to be valid.",
                "edit_summary": "Initial revision after community review.",
            },
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    result = await db_session.execute(
        select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
    )
    version = result.scalar_one()

    assert version.parent_version_id is None
    assert version.decision_reason == "Initial revision after community review."
    assert version.authored_by_id == author.id
    assert version.decided_by_id == author.id
    assert version.status == ProposalVersionStatus.accepted
    assert version.decided_at is not None


@pytest.mark.asyncio
async def test_second_edit_chains_parent_version_id(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
    db_session: AsyncSession,
) -> None:
    """
    Second edit: parent_version_id points to the first version's id.
    This creates the version chain required for Session 04.B history traversal.
    """
    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        # First edit
        await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "First edit for chain test",
                "description": "First edit description — long enough to pass validation here.",
                "edit_summary": "First edit to establish the chain.",
            },
        )
        # Second edit
        await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Second edit for chain test",
                "description": "Second edit description — long enough to pass validation here.",
                "edit_summary": "Second edit to verify parent chaining.",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    result = await db_session.execute(
        select(ProposalVersion)
        .where(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_number)
    )
    versions = list(result.scalars())
    assert len(versions) == 2

    v1, v2 = versions
    assert v1.parent_version_id is None
    assert v2.parent_version_id == v1.id


@pytest.mark.asyncio
async def test_audit_log_includes_version_id(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
    db_session: AsyncSession,
) -> None:
    """Audit log payload for PROPOSAL_EDITED includes version_id."""
    from app.models.audit import AuditEventType, AuditLog

    app.dependency_overrides[get_current_user] = _auth(author)
    try:
        resp = await client.patch(
            f"/api/v1/proposals/{proposal.id}",
            json={
                "title": "Audit version_id test",
                "description": "Audit test description — long enough to pass validation here.",
                "edit_summary": "Testing audit payload version_id field.",
            },
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    log_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.target_id == proposal.id,
            AuditLog.event_type == AuditEventType.PROPOSAL_EDITED,
        )
    )
    log_entry = log_result.scalar_one()
    assert "version_id" in log_entry.payload
    assert log_entry.payload["version_id"] is not None


# ---------------------------------------------------------------------------
# can_edit field on ProposalDetail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_edit_true_for_author_during_proposing(
    client: AsyncClient,
    proposal: Proposal,
    author: User,
) -> None:
    """GET /proposals/{id} returns can_edit=True for the author in PROPOSING phase."""
    auth_dep = _auth(author)
    app.dependency_overrides[get_current_user] = auth_dep
    app.dependency_overrides[get_optional_user] = auth_dep
    try:
        resp = await client.get(f"/api/v1/proposals/{proposal.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["can_edit"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.asyncio
async def test_can_edit_false_for_non_author(
    client: AsyncClient,
    proposal: Proposal,
    non_author: User,
) -> None:
    """GET /proposals/{id} returns can_edit=False for non-authors."""
    auth_dep = _auth(non_author)
    app.dependency_overrides[get_current_user] = auth_dep
    app.dependency_overrides[get_optional_user] = auth_dep
    try:
        resp = await client.get(f"/api/v1/proposals/{proposal.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["can_edit"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.asyncio
async def test_can_edit_false_for_author_in_voting_phase(
    client: AsyncClient,
    proposal_in_voting_thread: Proposal,
    author: User,
) -> None:
    """GET /proposals/{id} returns can_edit=False even for author when thread is VOTING."""
    auth_dep = _auth(author)
    app.dependency_overrides[get_current_user] = auth_dep
    app.dependency_overrides[get_optional_user] = auth_dep
    try:
        resp = await client.get(f"/api/v1/proposals/{proposal_in_voting_thread.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["can_edit"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.asyncio
async def test_can_edit_false_for_unauthenticated(
    client: AsyncClient,
    proposal: Proposal,
) -> None:
    """GET /proposals/{id} returns can_edit=False when not signed in (OptionalUser=None)."""
    resp = await client.get(f"/api/v1/proposals/{proposal.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["can_edit"] is False
