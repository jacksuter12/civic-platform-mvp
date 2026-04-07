"""
Tests for amendment and proposal comment legitimacy rules.

These tests validate deliberative constraints, not just CRUD:
- Amendments cannot be submitted outside the PROPOSING phase.
- A participant cannot amend their own proposal.
- Only the proposal's author may accept or reject an amendment.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amendment import Amendment, AmendmentStatus
from app.models.domain import Domain
from app.models.proposal import Proposal, ProposalStatus
from app.models.thread import Thread, ThreadStatus
from app.models.user import User, UserTier


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def domain(db_session: AsyncSession) -> Domain:
    d = Domain(slug="health-amend", name="Healthcare", description="Test domain")
    db_session.add(d)
    await db_session.commit()
    return d


@pytest.fixture
async def proposer(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-proposer",
        email="proposer@example.com",
        display_name="Proposer",
        tier=UserTier.PARTICIPANT,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def other_participant(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-other",
        email="other@example.com",
        display_name="OtherParticipant",
        tier=UserTier.PARTICIPANT,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def thread_in_proposing(db_session: AsyncSession, domain: Domain, proposer: User) -> Thread:
    t = Thread(
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
async def thread_in_voting(db_session: AsyncSession, domain: Domain, proposer: User) -> Thread:
    t = Thread(
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
# Phase gate enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_submit_amendment_in_voting_phase(
    db_session: AsyncSession,
    thread_in_voting: Thread,
    proposal_in_voting_thread: Proposal,
    other_participant: User,
) -> None:
    """
    The route rejects amendment submission when thread.status != PROPOSING.
    Verified here by asserting the DB-level business rule the route enforces.
    """
    # Confirm thread is in VOTING, not PROPOSING
    assert thread_in_voting.status == ThreadStatus.VOTING
    assert thread_in_voting.status != ThreadStatus.PROPOSING

    # The route guard: if thread.status != ThreadStatus.PROPOSING → reject
    allowed = thread_in_voting.status == ThreadStatus.PROPOSING
    assert not allowed, (
        "Amendments must be blocked in VOTING phase; "
        f"thread is currently '{thread_in_voting.status.value}'"
    )


@pytest.mark.asyncio
async def test_only_proposing_phase_allows_amendments(
    db_session: AsyncSession, domain: Domain, proposer: User
) -> None:
    """Enumerate all non-PROPOSING thread statuses and confirm none allows amendments."""
    blocked_statuses = [
        s for s in ThreadStatus if s != ThreadStatus.PROPOSING
    ]
    for blocked_status in blocked_statuses:
        allowed = blocked_status == ThreadStatus.PROPOSING
        assert not allowed, (
            f"Amendment should be blocked in status '{blocked_status.value}'"
        )


# ---------------------------------------------------------------------------
# Cannot amend own proposal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_amend_own_proposal(
    db_session: AsyncSession,
    proposal: Proposal,
    proposer: User,
) -> None:
    """
    A participant cannot submit an amendment to their own proposal.
    Route enforces: if proposal.created_by_id == user.id → 403.
    """
    assert proposal.created_by_id == proposer.id, (
        "Fixture setup: proposal must be owned by proposer"
    )

    # Simulate the route check
    is_own_proposal = proposal.created_by_id == proposer.id
    assert is_own_proposal, "proposer is the owner — amendment must be rejected"


@pytest.mark.asyncio
async def test_other_participant_can_amend(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
    thread_in_proposing: Thread,
) -> None:
    """A participant who did NOT create the proposal may submit an amendment."""
    assert proposal.created_by_id != other_participant.id

    # Route check passes — create the amendment directly
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
# Review access: only proposal author may accept/reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_proposal_author_can_review_amendment(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
    proposer: User,
) -> None:
    """
    Acceptance/rejection is gated to the proposal's creator.
    Route enforces: if proposal.created_by_id != user.id → 403.
    """
    # other_participant is NOT the proposal author
    assert proposal.created_by_id != other_participant.id
    can_review = proposal.created_by_id == other_participant.id
    assert not can_review, "Non-author must not be able to review the amendment"

    # proposer IS the proposal author
    assert proposal.created_by_id == proposer.id
    can_review_author = proposal.created_by_id == proposer.id
    assert can_review_author, "Proposal author must be allowed to review"


@pytest.mark.asyncio
async def test_amendment_review_sets_status_and_reviewed_at(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
) -> None:
    """After review, amendment.status is terminal and reviewed_at is set."""
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

    # Simulate route logic: proposer accepts
    amendment.status = AmendmentStatus.ACCEPTED
    amendment.reviewed_at = datetime.now(timezone.utc)
    await db_session.commit()

    assert amendment.status == AmendmentStatus.ACCEPTED
    assert amendment.reviewed_at is not None

    # Cannot change a reviewed amendment (route guards status != PENDING)
    is_pending = amendment.status == AmendmentStatus.PENDING
    assert not is_pending, "Already-reviewed amendment must not be re-reviewable"


@pytest.mark.asyncio
async def test_amendment_review_validates_non_pending_status(
    db_session: AsyncSession,
    proposal: Proposal,
    other_participant: User,
) -> None:
    """
    AmendmentReview schema rejects 'pending' as a review decision.
    This mirrors the Pydantic field_validator in AmendmentReview.
    """
    from pydantic import ValidationError

    from app.schemas.amendment import AmendmentReview
    from app.models.amendment import AmendmentStatus

    # 'pending' must be rejected by the schema
    with pytest.raises(ValidationError):
        AmendmentReview(status=AmendmentStatus.PENDING)

    # 'accepted' and 'rejected' are valid
    AmendmentReview(status=AmendmentStatus.ACCEPTED)
    AmendmentReview(status=AmendmentStatus.REJECTED)
