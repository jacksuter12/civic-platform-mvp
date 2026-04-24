"""
Unit tests for app.api.v1._annotation_perms.require_can_annotate.

Tests verify the permission and phase-gate logic without going through
the full HTTP stack. Each scenario exercises a distinct branch.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._annotation_perms import require_can_annotate
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
        slug="perms-test-community",
        name="Perms Test Community",
        description="Used for _annotation_perms tests.",
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
        slug="perms-domain",
        name="Perms Domain",
        description="Domain for perms tests.",
    )
    db_session.add(d)
    await db_session.commit()
    return d


@pytest_asyncio.fixture
async def annotator_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-annotator-perms",
        email="annotator-perms@example.com",
        display_name="AnnotatorPerms",
        tier=UserTier.REGISTERED,
        is_annotator=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def plain_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-plain-perms",
        email="plain-perms@example.com",
        display_name="PlainPerms",
        tier=UserTier.REGISTERED,
        is_annotator=False,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def member_user(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-member-perms",
        email="member-perms@example.com",
        display_name="MemberPerms",
        tier=UserTier.REGISTERED,
        is_annotator=False,
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
async def non_member_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-nonmember-perms",
        email="nonmember-perms@example.com",
        display_name="NonMemberPerms",
        tier=UserTier.REGISTERED,
        is_annotator=False,
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _make_proposal(
    db_session: AsyncSession,
    community: Community,
    domain: Domain,
    author: User,
    thread_status: ThreadStatus,
) -> tuple[Thread, Proposal]:
    thread = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=author.id,
        title="A deliberation thread",
        prompt="What should we do about the community center?",
        status=thread_status,
    )
    db_session.add(thread)
    await db_session.flush()

    proposal = Proposal(
        thread_id=thread.id,
        created_by_id=author.id,
        title="Build a community center",
        description="We should build a new community center for everyone.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(proposal)
    await db_session.commit()
    return thread, proposal


# ---------------------------------------------------------------------------
# Wiki annotation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wiki_annotator_can_annotate(
    db_session: AsyncSession, annotator_user: User
) -> None:
    result = await require_can_annotate(
        db_session, annotator_user, "wiki", "healthcare/overview"
    )
    assert result == (None, None)


@pytest.mark.asyncio
async def test_wiki_non_annotator_blocked(
    db_session: AsyncSession, plain_user: User
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_can_annotate(
            db_session, plain_user, "wiki", "healthcare/overview"
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Proposal annotation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proposal_in_proposing_registered_member_can_annotate(
    db_session: AsyncSession,
    community: Community,
    domain: Domain,
    member_user: User,
) -> None:
    thread, proposal = await _make_proposal(
        db_session, community, domain, member_user, ThreadStatus.PROPOSING
    )
    result_proposal, result_thread = await require_can_annotate(
        db_session, member_user, "proposal", str(proposal.id)
    )
    assert result_proposal is not None
    assert result_thread is not None
    assert result_proposal.id == proposal.id


@pytest.mark.asyncio
async def test_proposal_in_proposing_non_member_blocked(
    db_session: AsyncSession,
    community: Community,
    domain: Domain,
    member_user: User,
    non_member_user: User,
) -> None:
    thread, proposal = await _make_proposal(
        db_session, community, domain, member_user, ThreadStatus.PROPOSING
    )
    with pytest.raises(HTTPException) as exc_info:
        await require_can_annotate(
            db_session, non_member_user, "proposal", str(proposal.id)
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_proposal_in_deliberating_member_blocked(
    db_session: AsyncSession,
    community: Community,
    domain: Domain,
    member_user: User,
) -> None:
    thread, proposal = await _make_proposal(
        db_session, community, domain, member_user, ThreadStatus.DELIBERATING
    )
    with pytest.raises(HTTPException) as exc_info:
        await require_can_annotate(
            db_session, member_user, "proposal", str(proposal.id)
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_proposal_in_voting_member_blocked(
    db_session: AsyncSession,
    community: Community,
    domain: Domain,
    member_user: User,
) -> None:
    thread, proposal = await _make_proposal(
        db_session, community, domain, member_user, ThreadStatus.VOTING
    )
    with pytest.raises(HTTPException) as exc_info:
        await require_can_annotate(
            db_session, member_user, "proposal", str(proposal.id)
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Unsupported target_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_target_type_returns_400(
    db_session: AsyncSession, plain_user: User
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_can_annotate(
            db_session, plain_user, "document", "doc-id-123"
        )
    assert exc_info.value.status_code == 400
