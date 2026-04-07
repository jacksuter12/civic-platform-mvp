import uuid
from datetime import datetime

from pydantic import Field

from app.models.thread import ThreadStatus
from app.models.signal import SignalType
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic


class ThreadCreate(CamelBase):
    domain_id: uuid.UUID
    title: str = Field(min_length=10, max_length=200)
    prompt: str = Field(
        min_length=50,
        max_length=2000,
        description="The deliberation question. Be specific and non-leading.",
    )
    context: str = Field(
        default="",
        max_length=5000,
        description="Background information to inform participants.",
    )


class SignalCounts(CamelBase):
    support: int = 0
    concern: int = 0
    need_info: int = 0
    block: int = 0
    total: int = 0


class ThreadSummary(UUIDSchema, TimestampSchema):
    """Lightweight list item."""

    domain_id: uuid.UUID
    domain_name: str
    domain_slug: str
    title: str
    status: ThreadStatus
    signal_counts: SignalCounts
    post_count: int
    proposal_count: int
    phase_ends_at: datetime | None


class ThreadDetail(ThreadSummary):
    """Full thread with context."""

    prompt: str
    context: str
    created_by: UserPublic
    my_signal: SignalType | None = None  # set from auth context


class ThreadPhaseAdvance(CamelBase):
    """Facilitator advances the thread to the next phase."""

    target_status: ThreadStatus
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Recorded in audit log. Visible to all participants.",
    )
    phase_ends_at: datetime | None = None
