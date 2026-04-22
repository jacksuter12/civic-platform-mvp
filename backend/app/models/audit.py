import uuid
from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AuditEventType(str, PyEnum):
    # Identity
    USER_REGISTERED = "user_registered"
    USER_TIER_CHANGED = "user_tier_changed"
    USER_DEACTIVATED = "user_deactivated"
    # Threads
    THREAD_CREATED = "thread_created"
    THREAD_PHASE_ADVANCED = "thread_phase_advanced"
    # Posts
    POST_CREATED = "post_created"
    POST_REMOVED = "post_removed"
    # Signals
    SIGNAL_CAST = "signal_cast"
    SIGNAL_UPDATED = "signal_updated"
    # Proposals
    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_SUBMITTED = "proposal_submitted"
    PROPOSAL_STATUS_CHANGED = "proposal_status_changed"
    PROPOSAL_EDITED = "proposal_edited"
    # Voting
    VOTE_CAST = "vote_cast"
    # Allocation
    ALLOCATION_DECIDED = "allocation_decided"
    # Facilitator requests
    FACILITATOR_REQUEST_SUBMITTED = "facilitator_request_submitted"
    FACILITATOR_REQUEST_APPROVED = "facilitator_request_approved"
    FACILITATOR_REQUEST_DENIED = "facilitator_request_denied"
    # Profile
    DISPLAY_NAME_CHANGED = "display_name_changed"
    # Proposal comments
    PROPOSAL_COMMENT_CREATED = "proposal_comment_created"
    PROPOSAL_COMMENT_REMOVED = "proposal_comment_removed"
    # Amendments
    AMENDMENT_SUBMITTED = "amendment_submitted"
    AMENDMENT_ACCEPTED = "amendment_accepted"
    AMENDMENT_REJECTED = "amendment_rejected"
    # Annotations
    ANNOTATION_CREATED = "annotation_created"
    ANNOTATION_UPDATED = "annotation_updated"
    ANNOTATION_DELETED = "annotation_deleted"
    ANNOTATION_REACTION_ADDED = "annotation_reaction_added"
    ANNOTATION_REACTION_REMOVED = "annotation_reaction_removed"
    USER_ANNOTATOR_GRANTED = "user_annotator_granted"
    USER_ANNOTATOR_REVOKED = "user_annotator_revoked"
    # Community
    COMMUNITY_CREATED = "community_created"
    COMMUNITY_MEMBER_JOINED = "community_member_joined"
    COMMUNITY_MEMBER_PROMOTED = "community_member_promoted"
    # LLM (future)
    LLM_SUMMARY_GENERATED = "llm_summary_generated"


class AuditLog(Base, UUIDPKMixin, TimestampMixin):
    """
    Append-only transparency log. Every significant action produces a record here.

    Application-layer enforcement: the core.audit module only provides
    log_event(), never update or delete operations.

    Future hardening: add a PostgreSQL trigger to prevent UPDATE/DELETE,
    and revoke those privileges from the application DB role.

    This table is the primary public accountability surface.
    """

    __tablename__ = "audit_logs"

    event_type: Mapped[AuditEventType] = mapped_column(
        SAEnum(AuditEventType, name="audit_event_type"), nullable=False, index=True
    )
    # actor_id is None for system-initiated events
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # target_type: "thread", "post", "proposal", "vote", "allocation", etc.
    target_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    # JSON payload capturing the full event details at time of action
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Nullable: platform-level events (user registration, annotator grants, etc.)
    # have no community. Community-scoped events carry the community UUID.
    # Populated by log_event(community_id=...) once Session 3 route updates land.
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("communities.id"), nullable=True, index=True
    )
