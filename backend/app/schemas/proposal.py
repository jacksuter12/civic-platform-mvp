import uuid
from decimal import Decimal

from pydantic import Field, model_validator

from app.models.proposal import ProposalStatus
from app.models.vote import VoteChoice
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic


class ProposalCreate(CamelBase):
    title: str = Field(min_length=10, max_length=200)
    description: str = Field(min_length=50, max_length=5000)
    requested_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.01"),
        description="Amount requested from pool. None for non-monetary proposals.",
    )


class VoteSummary(CamelBase):
    yes: int = 0
    no: int = 0
    abstain: int = 0
    total: int = 0

    @property
    def passed(self) -> bool:
        if self.total == 0:
            return False
        return self.yes > self.no


class ProposalSummary(UUIDSchema, TimestampSchema):
    thread_id: uuid.UUID
    title: str
    description: str
    status: ProposalStatus
    requested_amount: Decimal | None
    vote_summary: VoteSummary
    my_vote: VoteChoice | None = None


class ProposalDetail(ProposalSummary):
    description: str
    created_by: UserPublic


class ProposalStatusUpdate(CamelBase):
    """Facilitator changes proposal status."""

    new_status: ProposalStatus
    reason: str = Field(min_length=10, max_length=500)


class VoteCreate(CamelBase):
    choice: VoteChoice
    rationale: str | None = Field(default=None, max_length=500)


class AllocationCreate(CamelBase):
    """Admin records a final allocation decision."""

    pool_id: uuid.UUID
    proposal_id: uuid.UUID
    amount: Decimal = Field(gt=Decimal("0"))
    rationale: str = Field(min_length=20, max_length=2000)

    @model_validator(mode="after")
    def amount_must_be_positive(self) -> "AllocationCreate":
        if self.amount <= 0:
            raise ValueError("amount must be positive")
        return self
