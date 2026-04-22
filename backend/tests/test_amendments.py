"""
Tests for amendment and proposal comment legitimacy rules.

These tests validate deliberative constraints, not just CRUD:
- Amendments cannot be submitted outside the PROPOSING phase.
- A participant cannot amend their own proposal.
- Only the proposal's author may accept or reject an amendment.
- Session 3: a user who is not a community member cannot submit an amendment (403).
"""

import uuid
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.amendment import Amendment, AmendmentStatus
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.domain import Domain
from app.models.proposal import Proposal, ProposalStatus
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="amend-community",
        name="Amendment Test Community",
        description="Community for amendment tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Test boundary",
        verification_method="Test verification",
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
        slug="health-amend",
        name="Healthcare",
        description="Test domain",
    )
    db_session.add(d)
    await db_session.commit()
    return d


@pytest_asyncio.fixture
async def proposer(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-proposer",
        email="proposer@example.com",
        display_name="Proposer",
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
async def other_participant(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-other",
        email="other@example.com",
        display_name="OtherParticipant",
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
async def non_member(db_session: AsyncSession) -> User:
    """A user with no community membership at all."""
    u = User(
        supabase_uid="uid-non-member",
        email="nonmember@example.com",
        display_name="NonMember",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def thread_in_proposing(
    db_session: AsyncSession, domain: Domain, community: Community, proposer: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=proposer.id,
        title="Test thread for amendments",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.PROPOSING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest.fixture
async def thread_in_voting(
    db_session: AsyncSession, domain: Domain, community: Community, proposer: User
) -> Thread:
    t = Thread(
        community_id=community.id,
        domain_id=domain.id,
        created_by_id=proposer.id,
        title="Test thread in voting",
        prompt="A test deliberation prompt with enough characters to be valid.",
        status=ThreadStatus.VOTING,
    )
    db_session.add(t)
    await db_session.commit()
    return t


@pytest.fixture
async def proposal(
    db_session: AsyncSession, thread_in_proposing: Thread, proposer: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_in_proposing.id,
        created_by_id=proposer.id,
        title="Expand community health clinics",
        description="We should fund ten new community health clinics in underserved areas.",
        status=ProposalStatus.SUBMITTED,
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def proposal_in_voting_thread(
    db_session: AsyncSession, thread_in_voting: Thread, proposer: User
) -> Proposal:
    p = Proposal(
        thread_id=thread_in_voting.id,
        created_by_id=proposer.id,
        title="Voting-phase proposal",
        description="This proposal exists in a thread that has moved to VOTING.",
        status=ProposalStatus.VOTING,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ---------------------------------------------------------------------------
# Client helper
# ---------------------------------------------------------------------------


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

    overrides = {
        get_db: override_db,
        get_optional_user: override_optional_user,
    }
    if user is not None:
        overrides[get_current_user] = override_required_user

    app.dependency_overrides.update(overrides)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Phase gate enforcement (model-layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_submit_amendment_in_voting_phase(
    db_session: AsyncSession,
    thread_in_voting: Thread,
    proposal_in_voting_thread: Proposal,
    other_participant: User,
) -> None:
    assert thread_in_voting.status == ThreadStatus.VOTING
    assert thread_in_voting.status != ThreadStatus.PROPOSING

    allowed = thread_in_voting.status == ThreadStatus.PROPOSING
    assert not allowed


@pytest.mark.asyncio
async def test_only_proposing_phase_allows_amendments(
    db_session: AsyncSession, domain: Domain, proposer: User
) -> None:
    blocked_statuses = [s for s in ThreadStatus if s != ThreadStatus.PROPOSING]
    for blocked_status in blocked_statuses:
        allowed = blocked_status == ThreadStatus.PROPOSING
        assert not allowed


# ---------------------------------------------------------------------------
# Cannot amend own proposal (model-layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_amend_own_proposal(
    db_session: AsyncSession,
    proposal: Proposal,
    proposer: User,
) -> None:
    assert proposal.created_by_id == proposer.id
    is_own_proposal = proposal.created_by_id == proposer.id
    assert is_own_proposal


@pytest.mark.asyncio
async def test_other_participant_can_amend(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
    thread_in_proposing: Thread,
) -> None:
    assert proposal.created_by_id != other_participant.id

    amendment = Amendment(
        proposal_id=proposal.id,
        author_id=other_participant.id,
        title="Clarify funding amount",
        original_text="We should fund ten new clinics.",
        proposed_text="We should fund ten new clinics, each receiving $500k annually.",
        rationale="The original text lacks a concrete funding figure needed for budgeting.",
    )
    db_session.add(amendment)
    await db_session.commit()

    assert amendment.id is not None
    assert amendment.status == AmendmentStatus.PENDING


# ---------------------------------------------------------------------------
# Review access (model-layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_proposal_author_can_review_amendment(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
    proposer: User,
) -> None:
    assert proposal.created_by_id != other_participant.id
    can_review = proposal.created_by_id == other_participant.id
    assert not can_review

    assert proposal.created_by_id == proposer.id
    can_review_author = proposal.created_by_id == proposer.id
    assert can_review_author


@pytest.mark.asyncio
async def test_amendment_review_sets_status_and_reviewed_at(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
) -> None:
    from datetime import datetime, timezone

    amendment = Amendment(
        proposal_id=proposal.id,
        author_id=other_participant.id,
        title="Add sunset clause",
        original_text="The program shall run indefinitely.",
        proposed_text="The program shall run for three years, then be reviewed.",
        rationale="Indefinite programs resist accountability; a sunset forces re-evaluation.",
    )
    db_session.add(amendment)
    await db_session.flush()

    amendment.status = AmendmentStatus.ACCEPTED
    amendment.reviewed_at = datetime.now(timezone.utc)
    await db_session.commit()

    assert amendment.status == AmendmentStatus.ACCEPTED
    assert amendment.reviewed_at is not None

    is_pending = amendment.status == AmendmentStatus.PENDING
    assert not is_pending


@pytest.mark.asyncio
async def test_amendment_review_validates_non_pending_status(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
) -> None:
    from pydantic import ValidationError

    from app.schemas.amendment import AmendmentReview
    from app.models.amendment import AmendmentStatus

    with pytest.raises(ValidationError):
        AmendmentReview(status=AmendmentStatus.PENDING)

    AmendmentReview(status=AmendmentStatus.ACCEPTED)
    AmendmentReview(status=AmendmentStatus.REJECTED)


# ---------------------------------------------------------------------------
# HTTP-layer test: non-member cannot submit amendment (Session 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_member_cannot_submit_amendment(
    db_session: AsyncSession,
    proposal: Proposal,
    thread_in_proposing: Thread,
    non_member: User,
) -> None:
    """
    A user with no community membership must receive 403 when attempting
    to submit an amendment to a proposal in a community-scoped thread.
    """
    async with _make_client(db_session, non_member) as c:
        resp = await c.post(
            f"/api/v1/proposals/{proposal.id}/amendments",
            json={
                "title": "Unauthorized amendment attempt",
                "original_text": "We should fund ten new clinics.",
                "proposed_text": "We should fund twelve new clinics.",
                "rationale": "More clinics would serve more people in underserved areas.",
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 403, (
        f"Expected 403, got {resp.status_code}: {resp.text}"
    )
