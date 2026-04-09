# Import all models so that alembic autogenerate sees them
from app.models.base import Base
from app.models.user import User, UserTier
from app.models.domain import Domain
from app.models.thread import Thread, ThreadStatus, VALID_TRANSITIONS
from app.models.post import Post
from app.models.signal import Signal, SignalType
from app.models.proposal import Proposal, ProposalStatus
from app.models.vote import Vote, VoteChoice
from app.models.pool import FundingPool
from app.models.allocation import AllocationDecision
from app.models.audit import AuditLog, AuditEventType
from app.models.facilitator_request import FacilitatorRequest, FacilitatorRequestStatus
from app.models.proposal_comment import ProposalComment
from app.models.amendment import Amendment, AmendmentStatus
from app.models.proposal_version import ProposalVersion
from app.models.annotation import Annotation, AnnotationReaction, AnnotationTargetType, ReactionType

__all__ = [
    "Base",
    "User",
    "UserTier",
    "Domain",
    "Thread",
    "ThreadStatus",
    "VALID_TRANSITIONS",
    "Post",
    "Signal",
    "SignalType",
    "Proposal",
    "ProposalStatus",
    "Vote",
    "VoteChoice",
    "FundingPool",
    "AllocationDecision",
    "AuditLog",
    "AuditEventType",
    "FacilitatorRequest",
    "FacilitatorRequestStatus",
    "ProposalComment",
    "Amendment",
    "AmendmentStatus",
    "ProposalVersion",
    "Annotation",
    "AnnotationReaction",
    "AnnotationTargetType",
    "ReactionType",
]
