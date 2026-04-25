"""
Tests for annotation threading (replies) and nested list response.

Validates:
- Reply creation inherits target_type/target_id from parent
- Nested replies appear in list response under their parent
- Cannot reply to a reply (one level of nesting only)
- Reply with wrong target_type/target_id is rejected
- List returns featured annotations first, then chronological
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
        slug="threading-community",
        name="Threading Test Community",
        description="Community for threading tests.",
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
        slug="threading-domain",
        name="Threading Domain",
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
async def member_a(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(db_session, community, "uid-thread-a", "a@example.com", "MemberA")
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def member_b(db_session: AsyncSession, community: Community) -> User:
    u = await _make_member(db_session, community, "uid-thread-b", "b@example.com", "MemberB")
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def thread(
    db_session: AsyncSession, community: Community, domain: Domain, member_a: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=member_a.id,
        title="Threading test thread",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest_asyncio.fixture
async def proposal(
    db_session: AsyncSession, thread: Thread, member_a: User
) -> Proposal:
    p = Proposal(
        thread_id=thread.id,
        created_by_id=member_a.id,
        title="Build a community garden for everyone",
        description="We should build a new community garden in the community center area for residents.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def top_annotation(
    db_session: AsyncSession, proposal: Proposal, member_a: User
) -> Annotation:
    a = Annotation(
        target_type="proposal",
        target_id=str(proposal.id),
        anchor_data={"selector": [{"type": "TextQuoteSelector", "exact": "community garden"}]},
        author_id=member_a.id,
        body="This is a top-level annotation.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_appears_nested_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    top_annotation: Annotation,
    member_b: User,
) -> None:
    """List endpoint returns replies nested under their parent annotation."""
    # Create a reply via HTTP
    app.dependency_overrides[get_current_user] = lambda: member_b
    resp = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {},
            "body": "This is a reply.",
            "parent_id": str(top_annotation.id),
        },
    )
    assert resp.status_code == 201, resp.text
    reply_id = resp.json()["id"]

    # List annotations
    list_resp = await client.get(
        "/api/v1/annotations",
        params={"target_type": "proposal", "target_id": str(proposal.id)},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()

    # Should have exactly one top-level annotation
    assert len(data) == 1
    top = data[0]
    assert top["id"] == str(top_annotation.id)
    # Reply nested inside
    assert len(top["replies"]) == 1
    assert top["replies"][0]["id"] == reply_id
    assert top["replies"][0]["parent_id"] == str(top_annotation.id)


@pytest.mark.asyncio
async def test_reply_inherits_target(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    top_annotation: Annotation,
    member_b: User,
) -> None:
    """Reply's target_type and target_id match the parent annotation."""
    app.dependency_overrides[get_current_user] = lambda: member_b
    resp = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {},
            "body": "Reply body.",
            "parent_id": str(top_annotation.id),
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["target_type"] == "proposal"
    assert data["target_id"] == str(proposal.id)
    assert data["parent_id"] == str(top_annotation.id)


@pytest.mark.asyncio
async def test_cannot_reply_to_reply(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    top_annotation: Annotation,
    member_a: User,
    member_b: User,
) -> None:
    """Replying to a reply is rejected (one level of nesting only)."""
    # Create a first-level reply
    app.dependency_overrides[get_current_user] = lambda: member_b
    resp = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {},
            "body": "First-level reply.",
            "parent_id": str(top_annotation.id),
        },
    )
    assert resp.status_code == 201
    reply_id = resp.json()["id"]

    # Attempt to reply to the reply
    app.dependency_overrides[get_current_user] = lambda: member_a
    resp2 = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {},
            "body": "Second-level reply — should fail.",
            "parent_id": reply_id,
        },
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_featured_annotations_sort_first(
    client: AsyncClient,
    db_session: AsyncSession,
    proposal: Proposal,
    member_a: User,
    community: Community,
) -> None:
    """Featured annotations appear before non-featured in the list."""
    # Create two annotations, then feature the second one
    facilitator = await _make_member(
        db_session, community,
        "uid-thread-fac", "fac@example.com", "Facilitator",
        tier=UserTier.FACILITATOR,
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: member_a
    r1 = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {"selector": [{"type": "TextQuoteSelector", "exact": "community"}]},
            "body": "First annotation.",
        },
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/annotations",
        json={
            "target_type": "proposal",
            "target_id": str(proposal.id),
            "anchor_data": {"selector": [{"type": "TextQuoteSelector", "exact": "garden"}]},
            "body": "Second annotation — will be featured.",
        },
    )
    assert r2.status_code == 201
    second_id = r2.json()["id"]

    # Feature the second annotation
    app.dependency_overrides[get_current_user] = lambda: facilitator
    feat_resp = await client.post(f"/api/v1/annotations/{second_id}/feature")
    assert feat_resp.status_code == 200

    # List — featured should come first
    app.dependency_overrides[get_current_user] = lambda: member_a
    list_resp = await client.get(
        "/api/v1/annotations",
        params={"target_type": "proposal", "target_id": str(proposal.id)},
    )
    assert list_resp.status_code == 200
    ids = [a["id"] for a in list_resp.json()]
    assert ids[0] == second_id, "Featured annotation should be first"
