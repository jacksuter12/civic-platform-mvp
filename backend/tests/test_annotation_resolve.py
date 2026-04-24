"""
Endpoint tests for annotation resolve/unresolve.

Tests verify:
- Annotation author can resolve their own annotation
- Proposal author (created_by_id) can resolve any annotation on their proposal
- Facilitator can resolve any annotation in their community
- Non-member returns 403
- Registered member who is neither author nor facilitator returns 403
- Resolving already-resolved returns 409
- Cannot resolve when thread is in VOTING (403)
- Unresolve restores open state
- Unresolving an unresolved annotation returns 409
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.main import app
from app.models.annotation import Annotation
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
        slug="resolve-test-community",
        name="Resolve Test Community",
        description="Community for resolve/unresolve tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Some boundary",
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
        slug="resolve-domain",
        name="Resolve Domain",
        description="Domain for resolve tests.",
    )
    db_session.add(d)
    await db_session.commit()
    return d


async def _make_user(
    db_session: AsyncSession,
    uid: str,
    email: str,
    name: str,
    tier: UserTier = UserTier.REGISTERED,
) -> User:
    u = User(
        supabase_uid=uid,
        email=email,
        display_name=name,
        tier=tier,
        is_annotator=False,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _join(
    db_session: AsyncSession,
    community: Community,
    user: User,
    tier: UserTier = UserTier.REGISTERED,
) -> None:
    m = CommunityMembership(
        community_id=community.id,
        user_id=user.id,
        tier=tier,
        joined_at=datetime.now(UTC),
    )
    db_session.add(m)
    await db_session.flush()


@pytest_asyncio.fixture
async def proposal_author(db_session: AsyncSession, community: Community) -> User:
    u = await _make_user(db_session, "uid-prop-author", "prop-author@example.com", "PropAuthor")
    await _join(db_session, community, u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def annotation_author(db_session: AsyncSession, community: Community) -> User:
    u = await _make_user(db_session, "uid-ann-author", "ann-author@example.com", "AnnAuthor")
    await _join(db_session, community, u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def facilitator(db_session: AsyncSession, community: Community) -> User:
    u = await _make_user(db_session, "uid-facilitator", "facilitator@example.com", "Facilitator")
    await _join(db_session, community, u, tier=UserTier.FACILITATOR)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def registered_bystander(db_session: AsyncSession, community: Community) -> User:
    """Registered member — not annotation author, not proposal author, not facilitator."""
    u = await _make_user(db_session, "uid-bystander", "bystander@example.com", "Bystander")
    await _join(db_session, community, u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def non_member(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, "uid-non-member-r", "non-member-r@example.com", "NonMemberR")
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def thread_proposing(
    db_session: AsyncSession, community: Community, domain: Domain, proposal_author: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=proposal_author.id,
        title="Resolve test thread",
        prompt="What should we build?",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def thread_voting(
    db_session: AsyncSession, community: Community, domain: Domain, proposal_author: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=proposal_author.id,
        title="Voting phase thread",
        prompt="Time to vote on things.",
        status=ThreadStatus.VOTING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def proposal(
    db_session: AsyncSession, thread_proposing: Thread, proposal_author: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_proposing.id,
        created_by_id=proposal_author.id,
        title="Build a new park",
        description="We should build a new park in the community center area.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def annotation(
    db_session: AsyncSession, proposal: Proposal, annotation_author: User
) -> Annotation:
    a = Annotation(
        target_type="proposal",
        target_id=str(proposal.id),
        anchor_data={"type": "TextQuoteSelector", "exact": "community center"},
        author_id=annotation_author.id,
        body="This needs more detail about the design.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


@pytest_asyncio.fixture
async def proposal_in_voting(
    db_session: AsyncSession, thread_voting: Thread, proposal_author: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_voting.id,
        created_by_id=proposal_author.id,
        title="Build a parking lot",
        description="We should build a parking lot near the city hall.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def annotation_in_voting(
    db_session: AsyncSession, proposal_in_voting: Proposal, annotation_author: User
) -> Annotation:
    a = Annotation(
        target_type="proposal",
        target_id=str(proposal_in_voting.id),
        anchor_data={"type": "TextQuoteSelector", "exact": "parking lot"},
        author_id=annotation_author.id,
        body="Why a parking lot?",
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _auth_as(user: User):
    def _dep():
        return user
    return _dep


# ---------------------------------------------------------------------------
# Resolve tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_annotation_author_can_resolve(
    client: AsyncClient,
    annotation: Annotation,
    annotation_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotation_author)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved_at"] is not None
        assert data["resolved_by_id"] == str(annotation_author.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_proposal_author_can_resolve(
    client: AsyncClient,
    annotation: Annotation,
    proposal_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(proposal_author)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved_at"] is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_facilitator_can_resolve(
    client: AsyncClient,
    annotation: Annotation,
    facilitator: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(facilitator)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_non_member_cannot_resolve(
    client: AsyncClient,
    annotation: Annotation,
    non_member: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(non_member)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_registered_bystander_cannot_resolve(
    client: AsyncClient,
    annotation: Annotation,
    registered_bystander: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(registered_bystander)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_resolve_already_resolved_returns_409(
    client: AsyncClient,
    annotation: Annotation,
    annotation_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotation_author)
    try:
        resp1 = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp1.status_code == 200
        resp2 = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp2.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_cannot_resolve_in_voting_phase(
    client: AsyncClient,
    annotation_in_voting: Annotation,
    annotation_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotation_author)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation_in_voting.id}/resolve")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Unresolve tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolve_restores_open_state(
    client: AsyncClient,
    annotation: Annotation,
    annotation_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotation_author)
    try:
        resp1 = await client.post(f"/api/v1/annotations/{annotation.id}/resolve")
        assert resp1.status_code == 200
        assert resp1.json()["resolved_at"] is not None

        resp2 = await client.post(f"/api/v1/annotations/{annotation.id}/unresolve")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["resolved_at"] is None
        assert data["resolved_by_id"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unresolve_unresolved_returns_409(
    client: AsyncClient,
    annotation: Annotation,
    annotation_author: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotation_author)
    try:
        resp = await client.post(f"/api/v1/annotations/{annotation.id}/unresolve")
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)
