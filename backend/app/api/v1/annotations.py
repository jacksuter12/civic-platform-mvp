"""
Annotation routes — CRUD for annotations and their reactions.

Permission summary:
  GET    /annotations                   — public (no auth required)
  POST   /annotations                   — wiki: annotator; proposal: registered member in PROPOSING
  PATCH  /annotations/{id}              — annotation author or admin
  DELETE /annotations/{id}              — author self-deletes; moderator deletes others'
  POST   /annotations/{id}/reactions    — wiki: annotator; proposal: registered member in PROPOSING
  DELETE /annotations/{id}/reactions    — same as POST reactions
  POST   /annotations/{id}/resolve      — annotation author, proposal author, or facilitator
  POST   /annotations/{id}/unresolve    — same as resolve

Admin annotator grant/revoke lives in admin.py (routes 7-8).

All mutation routes write to the audit log inside the same DB transaction.
Rate limiting is not implemented here — note for future operational setup.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, OptionalUser
from app.api.v1._annotation_perms import (
    require_can_annotate,
    require_can_moderate,
    require_can_resolve,
)
from app.core.audit import log_event
from app.models.annotation import (
    Annotation,
    AnnotationReaction,
    AnnotationTargetType,
    ReactionType,
)
from app.models.audit import AuditEventType
from app.models.user import UserTier
from app.schemas.annotation import (
    AnnotationCreate,
    AnnotationReactionCreate,
    AnnotationReactionState,
    AnnotationRead,
    AnnotationUpdate,
    ReactionCounts,
)
from app.schemas.user import UserPublic

router = APIRouter()

TOMBSTONE = "[deleted]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reaction_state(
    annotation: Annotation, current_user_id: uuid.UUID | None
) -> tuple[ReactionCounts, ReactionType | None]:
    """Compute reaction counts and the requesting user's own reaction."""
    endorse = sum(1 for r in annotation.reactions if r.reaction == ReactionType.ENDORSE)
    needs_work = sum(
        1 for r in annotation.reactions if r.reaction == ReactionType.NEEDS_WORK
    )
    my_reaction: ReactionType | None = None
    if current_user_id:
        for r in annotation.reactions:
            if r.user_id == current_user_id:
                my_reaction = r.reaction
                break
    return ReactionCounts(endorse=endorse, needs_work=needs_work), my_reaction


def _to_read(
    annotation: Annotation, current_user_id: uuid.UUID | None
) -> AnnotationRead:
    """Convert an ORM Annotation (with loaded author + reactions) to AnnotationRead."""
    counts, my_reaction = _reaction_state(annotation, current_user_id)
    body = TOMBSTONE if annotation.deleted_at is not None else annotation.body
    return AnnotationRead(
        id=annotation.id,
        created_at=annotation.created_at,
        target_type=annotation.target_type,
        target_id=annotation.target_id,
        anchor_data=annotation.anchor_data,
        author=UserPublic.model_validate(annotation.author),
        parent_id=annotation.parent_id,
        body=body,
        updated_at=annotation.updated_at,
        deleted_at=annotation.deleted_at,
        resolved_at=annotation.resolved_at,
        resolved_by_id=annotation.resolved_by_id,
        reactions=counts,
        my_reaction=my_reaction,
    )


async def _get_annotation_or_404(db: DB, annotation_id: uuid.UUID) -> Annotation:
    result = await db.execute(
        select(Annotation)
        .options(
            selectinload(Annotation.author),
            selectinload(Annotation.reactions),
        )
        .where(Annotation.id == annotation_id)
    )
    annotation = result.scalar_one_or_none()
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found.")
    return annotation


# ---------------------------------------------------------------------------
# Route 1 — GET /annotations
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AnnotationRead])
async def list_annotations(
    db: DB,
    current_user: OptionalUser,
    target_type: Annotated[AnnotationTargetType, Query()],
    target_id: Annotated[str, Query(min_length=1, max_length=255)],
    include_deleted: Annotated[bool, Query()] = False,
) -> list[AnnotationRead]:
    """
    Return all annotations on a given target, chronological order.
    No auth required. include_deleted is respected only for admin requesters.
    """
    query = (
        select(Annotation)
        .options(
            selectinload(Annotation.author),
            selectinload(Annotation.reactions),
        )
        .where(
            Annotation.target_type == target_type,
            Annotation.target_id == target_id,
        )
        .order_by(Annotation.created_at.asc())
    )

    is_admin = current_user is not None and current_user.tier == UserTier.ADMIN
    if not (include_deleted and is_admin):
        query = query.where(Annotation.deleted_at.is_(None))

    result = await db.execute(query)
    annotations = list(result.scalars())

    current_user_id = current_user.id if current_user else None
    return [_to_read(a, current_user_id) for a in annotations]


# ---------------------------------------------------------------------------
# Route 2 — POST /annotations
# ---------------------------------------------------------------------------


@router.post("", response_model=AnnotationRead, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    payload: AnnotationCreate,
    user: CurrentUser,
    db: DB,
) -> AnnotationRead:
    """
    Create a new annotation. Permission branches on target_type:
    - wiki: requires annotator capability
    - proposal: requires registered community membership + PROPOSING phase
    """
    if payload.parent_id is not None:
        parent_result = await db.execute(
            select(Annotation).where(Annotation.id == payload.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent annotation not found.")
        same_target = (
            parent.target_type == payload.target_type
            and parent.target_id == payload.target_id
        )
        if not same_target:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parent annotation must be on the same target.",
            )
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot reply to a reply. One level of nesting only.",
            )

    proposal, thread = await require_can_annotate(
        db, user, payload.target_type.value, payload.target_id
    )
    community_id = thread.community_id if thread is not None else None

    annotation = Annotation(
        target_type=payload.target_type,
        target_id=payload.target_id,
        anchor_data=payload.anchor_data,
        author_id=user.id,
        parent_id=payload.parent_id,
        body=payload.body,
    )
    db.add(annotation)
    await db.flush()

    audit_payload: dict = {
        "target_type": payload.target_type.value,
        "target_id": payload.target_id,
    }
    if payload.parent_id:
        audit_payload["parent_id"] = str(payload.parent_id)

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_CREATED,
        target_type="annotation",
        target_id=annotation.id,
        payload=audit_payload,
        actor_id=user.id,
        community_id=community_id,
    )

    await db.refresh(annotation, ["author", "reactions"])
    return _to_read(annotation, user.id)


# ---------------------------------------------------------------------------
# Route 3 — PATCH /annotations/{annotation_id}
# ---------------------------------------------------------------------------


@router.patch("/{annotation_id}", response_model=AnnotationRead)
async def update_annotation(
    annotation_id: uuid.UUID,
    payload: AnnotationUpdate,
    user: CurrentUser,
    db: DB,
) -> AnnotationRead:
    """Edit annotation body. Author or admin only."""
    annotation = await _get_annotation_or_404(db, annotation_id)

    if annotation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    is_admin = user.tier == UserTier.ADMIN
    is_author = annotation.author_id == user.id

    if not (is_author or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or an admin may edit this annotation.",
        )

    annotation.body = payload.body
    annotation.updated_at = datetime.now(UTC)
    db.add(annotation)
    await db.flush()

    audit_payload: dict = {"body": payload.body}
    if is_admin and not is_author:
        audit_payload["admin_override"] = True
        audit_payload["original_author_id"] = str(annotation.author_id)

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_UPDATED,
        target_type="annotation",
        target_id=annotation.id,
        payload=audit_payload,
        actor_id=user.id,
    )

    return _to_read(annotation, user.id)


# ---------------------------------------------------------------------------
# Route 4 — DELETE /annotations/{annotation_id}
# ---------------------------------------------------------------------------


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> None:
    """
    Soft-delete an annotation. Authors may delete their own. For others'
    annotations, permission is checked via require_can_moderate (which branches
    on target_type: wiki = annotator/admin; proposal = facilitator+).
    """
    annotation = await _get_annotation_or_404(db, annotation_id)

    if annotation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    is_author = annotation.author_id == user.id
    community_id = None

    if not is_author:
        _, thread = await require_can_moderate(db, user, annotation)
        community_id = thread.community_id if thread is not None else None

    original_body = annotation.body
    annotation.body = TOMBSTONE
    annotation.deleted_at = datetime.now(UTC)
    db.add(annotation)
    await db.flush()

    audit_payload: dict = {"original_body": original_body}
    if not is_author:
        audit_payload["moderated_by_id"] = str(user.id)
        audit_payload["original_author_id"] = str(annotation.author_id)

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_DELETED,
        target_type="annotation",
        target_id=annotation.id,
        payload=audit_payload,
        actor_id=user.id,
        community_id=community_id,
    )


# ---------------------------------------------------------------------------
# Route 5 — POST /annotations/{annotation_id}/reactions
# ---------------------------------------------------------------------------


@router.post(
    "/{annotation_id}/reactions",
    response_model=AnnotationReactionState,
)
async def add_reaction(
    annotation_id: uuid.UUID,
    payload: AnnotationReactionCreate,
    user: CurrentUser,
    db: DB,
) -> AnnotationReactionState:
    """
    Upsert a reaction on an annotation.
    Cannot react to own annotation. Cannot react to a deleted annotation.
    Permission branches on target_type: wiki = annotator; proposal = registered member.
    """
    annotation = await _get_annotation_or_404(db, annotation_id)

    if annotation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    if annotation.author_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot react to your own annotation.",
        )

    await require_can_annotate(db, user, annotation.target_type, annotation.target_id)

    existing_result = await db.execute(
        select(AnnotationReaction).where(
            AnnotationReaction.annotation_id == annotation_id,
            AnnotationReaction.user_id == user.id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    audit_payload: dict = {"reaction": payload.reaction.value}

    if existing is not None:
        if existing.reaction == payload.reaction:
            # No change — return current state without an audit entry
            counts, my_reaction = _reaction_state(annotation, user.id)
            return AnnotationReactionState(
                endorse=counts.endorse,
                needs_work=counts.needs_work,
                my_reaction=my_reaction,
            )
        audit_payload["old_reaction"] = existing.reaction.value
        existing.reaction = payload.reaction
        db.add(existing)
    else:
        reaction = AnnotationReaction(
            annotation_id=annotation_id,
            user_id=user.id,
            reaction=payload.reaction,
        )
        db.add(reaction)

    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_REACTION_ADDED,
        target_type="annotation",
        target_id=annotation_id,
        payload=audit_payload,
        actor_id=user.id,
    )

    await db.refresh(annotation, ["reactions"])
    counts, my_reaction = _reaction_state(annotation, user.id)
    return AnnotationReactionState(
        endorse=counts.endorse,
        needs_work=counts.needs_work,
        my_reaction=my_reaction,
    )


# ---------------------------------------------------------------------------
# Route 6 — DELETE /annotations/{annotation_id}/reactions
# ---------------------------------------------------------------------------


@router.delete("/{annotation_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reaction(
    annotation_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> None:
    """Remove the requesting user's reaction. Idempotent — 204 if no reaction exists."""
    annotation = await _get_annotation_or_404(db, annotation_id)

    if annotation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    await require_can_annotate(db, user, annotation.target_type, annotation.target_id)

    existing_result = await db.execute(
        select(AnnotationReaction).where(
            AnnotationReaction.annotation_id == annotation_id,
            AnnotationReaction.user_id == user.id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing is None:
        return  # idempotent — no audit entry

    original_reaction = existing.reaction
    await db.delete(existing)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_REACTION_REMOVED,
        target_type="annotation",
        target_id=annotation_id,
        payload={"reaction": original_reaction.value},
        actor_id=user.id,
    )


# ---------------------------------------------------------------------------
# Route 7 — POST /annotations/{annotation_id}/resolve
# ---------------------------------------------------------------------------


@router.post("/{annotation_id}/resolve", response_model=AnnotationRead)
async def resolve_annotation(
    annotation_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> AnnotationRead:
    """
    Mark an annotation as resolved. Only proposal annotations can be resolved.
    Permitted by: the annotation author, the proposal author, or a community facilitator.
    """
    annotation = await _get_annotation_or_404(db, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    if annotation.resolved_at is not None:
        raise HTTPException(status_code=409, detail="Already resolved.")

    proposal, thread = await require_can_resolve(db, user, annotation)

    annotation.resolved_at = datetime.now(UTC)
    annotation.resolved_by_id = user.id
    db.add(annotation)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_RESOLVED,
        target_type="annotation",
        target_id=annotation.id,
        payload={
            "annotation_id": str(annotation.id),
            "annotation_target_type": annotation.target_type,
            "resolved_by_id": str(user.id),
        },
        actor_id=user.id,
        community_id=thread.community_id,
    )

    await db.refresh(annotation, ["author", "reactions"])
    return _to_read(annotation, user.id)


# ---------------------------------------------------------------------------
# Route 8 — POST /annotations/{annotation_id}/unresolve
# ---------------------------------------------------------------------------


@router.post("/{annotation_id}/unresolve", response_model=AnnotationRead)
async def unresolve_annotation(
    annotation_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> AnnotationRead:
    """
    Mark a previously resolved annotation as open again. Only proposal annotations.
    Permitted by: the annotation author, the proposal author, or a community facilitator.
    """
    annotation = await _get_annotation_or_404(db, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found.")

    if annotation.resolved_at is None:
        raise HTTPException(status_code=409, detail="Annotation is not resolved.")

    proposal, thread = await require_can_resolve(db, user, annotation)

    annotation.resolved_at = None
    annotation.resolved_by_id = None
    db.add(annotation)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.ANNOTATION_UNRESOLVED,
        target_type="annotation",
        target_id=annotation.id,
        payload={
            "annotation_id": str(annotation.id),
            "annotation_target_type": annotation.target_type,
            "unresolved_by_id": str(user.id),
        },
        actor_id=user.id,
        community_id=thread.community_id,
    )

    await db.refresh(annotation, ["author", "reactions"])
    return _to_read(annotation, user.id)
