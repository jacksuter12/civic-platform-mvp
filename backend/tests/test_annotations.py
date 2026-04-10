"""
Annotation legitimacy tests.

Tests verify:
- Permission gates (annotator required to create/react; author/admin to edit/delete)
- Public read (no auth required)
- Soft-delete preserves row, tombstones body
- Reaction upsert cycle (insert → change → delete)
- Self-reaction prevention
- Reply-to-reply prevention (one level of nesting only)
- Annotator grant/revoke (admin only, idempotent, audit log)
- Audit log entries written for each action

These tests use the in-memory SQLite DB from conftest.py and override FastAPI
auth dependencies per-test to inject specific user contexts.
"""

import uuid
from datetime import UTC

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.main import app
from app.models.annotation import Annotation, AnnotationReaction, ReactionType
from app.models.audit import AuditEventType, AuditLog
from app.models.user import User, UserTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def annotator(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-annotator",
        email="annotator@example.com",
        display_name="Annotator",
        tier=UserTier.REGISTERED,
        is_annotator=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def other_annotator(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-other-annotator",
        email="other-annotator@example.com",
        display_name="OtherAnnotator",
        tier=UserTier.REGISTERED,
        is_annotator=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def plain_user(db_session: AsyncSession) -> User:
    """Registered user without annotator capability."""
    u = User(
        supabase_uid="uid-plain",
        email="plain@example.com",
        display_name="PlainUser",
        tier=UserTier.REGISTERED,
        is_annotator=False,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    u = User(
        supabase_uid="uid-admin",
        email="admin@example.com",
        display_name="Admin",
        tier=UserTier.ADMIN,
        is_annotator=False,  # admin implies capability without the flag
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def annotation(db_session: AsyncSession, annotator: User) -> Annotation:
    """A pre-existing annotation owned by the annotator fixture."""
    a = Annotation(
        target_type="wiki",
        target_id="healthcare/overview",
        anchor_data={"type": "TextQuoteSelector", "exact": "some text"},
        author_id=annotator.id,
        body="This is a test annotation.",
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ---------------------------------------------------------------------------
# Helper — override auth deps inside a test
# ---------------------------------------------------------------------------


def _auth_as(user: User):
    """Returns a sync callable suitable for dependency_overrides[get_current_user]."""
    def _dep():
        return user
    return _dep


def _optional_auth_as(user: User | None):
    def _dep():
        return user
    return _dep


# ---------------------------------------------------------------------------
# Test 1 — Annotator can create; non-annotator cannot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_annotator_can_create(client: AsyncClient, annotator: User) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "anchor_data": {"type": "TextQuoteSelector", "exact": "hello"},
                "body": "An annotation body.",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == "An annotation body."
        assert data["author"]["id"] == str(annotator.id)
        assert data["reactions"]["endorse"] == 0
        assert data["reactions"]["needs_work"] == 0
        assert data["my_reaction"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_non_annotator_cannot_create(
    client: AsyncClient, plain_user: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(plain_user)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "anchor_data": {"exact": "hello"},
                "body": "Should be blocked.",
            },
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_can_create_without_annotator_flag(
    client: AsyncClient, admin_user: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "anchor_data": {"exact": "hello"},
                "body": "Admin annotation.",
            },
        )
        assert resp.status_code == 201
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 2 — Anyone (including unauthenticated) can read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_can_read(
    client: AsyncClient, annotation: Annotation
) -> None:
    app.dependency_overrides[get_optional_user] = _optional_auth_as(None)
    try:
        resp = await client.get(
            "/api/v1/annotations",
            params={"target_type": "wiki", "target_id": "healthcare/overview"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["body"] == annotation.body
        assert data[0]["my_reaction"] is None
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.asyncio
async def test_authenticated_read_shows_my_reaction(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    other_annotator: User,
) -> None:
    # other_annotator reacts first
    reaction = AnnotationReaction(
        annotation_id=annotation.id,
        user_id=other_annotator.id,
        reaction=ReactionType.ENDORSE,
    )
    db_session.add(reaction)
    await db_session.commit()

    app.dependency_overrides[get_optional_user] = _optional_auth_as(other_annotator)
    try:
        resp = await client.get(
            "/api/v1/annotations",
            params={"target_type": "wiki", "target_id": "healthcare/overview"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["my_reaction"] == "endorse"
        assert data[0]["reactions"]["endorse"] == 1
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# Test 3 — Edit: author can; another annotator cannot; admin can
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_can_edit(
    client: AsyncClient, annotation: Annotation, annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.patch(
            f"/api/v1/annotations/{annotation.id}",
            json={"body": "Updated body."},
        )
        assert resp.status_code == 200
        assert resp.json()["body"] == "Updated body."
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_other_annotator_cannot_edit(
    client: AsyncClient, annotation: Annotation, other_annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(other_annotator)
    try:
        resp = await client.patch(
            f"/api/v1/annotations/{annotation.id}",
            json={"body": "Unauthorized edit."},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_can_edit_any_annotation(
    client: AsyncClient, annotation: Annotation, admin_user: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.patch(
            f"/api/v1/annotations/{annotation.id}",
            json={"body": "Admin override body."},
        )
        assert resp.status_code == 200
        assert resp.json()["body"] == "Admin override body."
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 4 — Soft delete preserves row, tombstones body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_tombstones_body(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    annotator: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.delete(f"/api/v1/annotations/{annotation.id}")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Row still exists
    result = await db_session.execute(
        select(Annotation).where(Annotation.id == annotation.id)
    )
    row = result.scalar_one()
    assert row.deleted_at is not None
    assert row.body == "[deleted]"


@pytest.mark.asyncio
async def test_deleted_annotation_excluded_from_default_list(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    annotator: User,
) -> None:
    from datetime import datetime

    annotation.body = "[deleted]"
    annotation.deleted_at = datetime.now(UTC)
    db_session.add(annotation)
    await db_session.commit()

    app.dependency_overrides[get_optional_user] = _optional_auth_as(None)
    try:
        resp = await client.get(
            "/api/v1/annotations",
            params={"target_type": "wiki", "target_id": "healthcare/overview"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.asyncio
async def test_admin_can_see_deleted_with_include_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    admin_user: User,
) -> None:
    from datetime import datetime

    annotation.body = "[deleted]"
    annotation.deleted_at = datetime.now(UTC)
    db_session.add(annotation)
    await db_session.commit()

    app.dependency_overrides[get_optional_user] = _optional_auth_as(admin_user)
    try:
        resp = await client.get(
            "/api/v1/annotations",
            params={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "include_deleted": "true",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["body"] == "[deleted]"
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# Test 5 — Reaction upsert cycle: insert → change → delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reaction_insert_change_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    other_annotator: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(other_annotator)
    try:
        # Insert endorse
        resp = await client.post(
            f"/api/v1/annotations/{annotation.id}/reactions",
            json={"reaction": "endorse"},
        )
        assert resp.status_code == 200
        assert resp.json()["my_reaction"] == "endorse"
        assert resp.json()["endorse"] == 1

        # Change to needs_work
        resp = await client.post(
            f"/api/v1/annotations/{annotation.id}/reactions",
            json={"reaction": "needs_work"},
        )
        assert resp.status_code == 200
        assert resp.json()["my_reaction"] == "needs_work"
        assert resp.json()["endorse"] == 0
        assert resp.json()["needs_work"] == 1

        # Remove
        resp = await client.delete(f"/api/v1/annotations/{annotation.id}/reactions")
        assert resp.status_code == 204

        # Confirm removed
        result = await db_session.execute(
            select(AnnotationReaction).where(
                AnnotationReaction.annotation_id == annotation.id,
                AnnotationReaction.user_id == other_annotator.id,
            )
        )
        assert result.scalar_one_or_none() is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 6 — Cannot react to own annotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_react_to_own_annotation(
    client: AsyncClient, annotation: Annotation, annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            f"/api/v1/annotations/{annotation.id}/reactions",
            json={"reaction": "endorse"},
        )
        assert resp.status_code == 400
        assert "own annotation" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 7 — Cannot create a reply to a reply (one level only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_reply_to_reply(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    annotator: User,
) -> None:
    # Create a reply to the top-level annotation
    reply = Annotation(
        target_type="wiki",
        target_id="healthcare/overview",
        anchor_data={"exact": "some text"},
        author_id=annotator.id,
        parent_id=annotation.id,
        body="A reply.",
    )
    db_session.add(reply)
    await db_session.commit()

    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "anchor_data": {"exact": "text"},
                "body": "Reply to a reply — should fail.",
                "parent_id": str(reply.id),
            },
        )
        assert resp.status_code == 422
        assert "nesting" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 8 — Annotator grant/revoke (admin only, idempotent, audit log)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_grants_annotator(
    client: AsyncClient,
    db_session: AsyncSession,
    plain_user: User,
    admin_user: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.post(
            f"/api/v1/admin/users/{plain_user.id}/annotator",
            json={"reason": "Trusted reviewer."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_annotator"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    await db_session.refresh(plain_user)
    assert plain_user.is_annotator is True


@pytest.mark.asyncio
async def test_admin_revokes_annotator(
    client: AsyncClient,
    db_session: AsyncSession,
    annotator: User,
    admin_user: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.delete(
            f"/api/v1/admin/users/{annotator.id}/annotator",
        )
        assert resp.status_code == 200
        assert resp.json()["is_annotator"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    await db_session.refresh(annotator)
    assert annotator.is_annotator is False


@pytest.mark.asyncio
async def test_non_admin_cannot_grant_annotator(
    client: AsyncClient, plain_user: User, annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            f"/api/v1/admin/users/{plain_user.id}/annotator",
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_grant_idempotent_no_duplicate_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    annotator: User,
    admin_user: User,
) -> None:
    """Granting annotator to someone who already has it: 200 but no new audit entry."""
    initial_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.USER_ANNOTATOR_GRANTED,
            AuditLog.target_id == annotator.id,
        )
    )
    initial_count = len(list(initial_result.scalars()))

    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.post(f"/api/v1/admin/users/{annotator.id}/annotator")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    after_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.USER_ANNOTATOR_GRANTED,
            AuditLog.target_id == annotator.id,
        )
    )
    after_count = len(list(after_result.scalars()))
    assert after_count == initial_count  # no new audit entry


# ---------------------------------------------------------------------------
# Test 9 — Audit log entries are written for each action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_on_create(
    client: AsyncClient, db_session: AsyncSession, annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "wiki",
                "target_id": "healthcare/overview",
                "anchor_data": {"exact": "text"},
                "body": "Audit test annotation.",
            },
        )
        assert resp.status_code == 201
        annotation_id = resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_CREATED,
            AuditLog.target_id == uuid.UUID(annotation_id),
        )
    )
    log = result.scalar_one()
    assert log.actor_id == annotator.id
    assert log.payload["target_type"] == "wiki"


@pytest.mark.asyncio
async def test_audit_log_on_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    annotator: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.delete(f"/api/v1/annotations/{annotation.id}")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_DELETED,
            AuditLog.target_id == annotation.id,
        )
    )
    log = result.scalar_one()
    assert log.actor_id == annotator.id
    assert "original_body" in log.payload


@pytest.mark.asyncio
async def test_audit_log_on_reaction(
    client: AsyncClient,
    db_session: AsyncSession,
    annotation: Annotation,
    other_annotator: User,
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(other_annotator)
    try:
        await client.post(
            f"/api/v1/annotations/{annotation.id}/reactions",
            json={"reaction": "endorse"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == AuditEventType.ANNOTATION_REACTION_ADDED,
            AuditLog.target_id == annotation.id,
        )
    )
    log = result.scalar_one()
    assert log.actor_id == other_annotator.id
    assert log.payload["reaction"] == "endorse"


# ---------------------------------------------------------------------------
# Test 10 — v1 rejects non-wiki target_type on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rejects_non_wiki_target(
    client: AsyncClient, annotator: User
) -> None:
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.post(
            "/api/v1/annotations",
            json={
                "target_type": "post",
                "target_id": "some-post-id",
                "anchor_data": {"exact": "text"},
                "body": "Should be rejected.",
            },
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Test 11 — GET /admin/users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_users_returns_all(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    annotator: User,
    plain_user: User,
) -> None:
    """Admin can fetch all users; response includes is_annotator and tier."""
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        ids = {u["id"] for u in data}
        assert str(admin_user.id) in ids
        assert str(annotator.id) in ids
        assert str(plain_user.id) in ids

        # annotator fixture has is_annotator=True
        annotator_row = next(u for u in data if u["id"] == str(annotator.id))
        assert annotator_row["is_annotator"] is True
        assert annotator_row["tier"] == "registered"

        # plain_user has is_annotator=False
        plain_row = next(u for u in data if u["id"] == str(plain_user.id))
        assert plain_row["is_annotator"] is False

        # email is included
        admin_row = next(u for u in data if u["id"] == str(admin_user.id))
        assert admin_row["email"] == admin_user.email
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(
    client: AsyncClient, annotator: User
) -> None:
    """Non-admin users get 403."""
    app.dependency_overrides[get_current_user] = _auth_as(annotator)
    try:
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_list_users_search_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    annotator: User,
    plain_user: User,
) -> None:
    """Search parameter filters by display_name or email substring."""
    app.dependency_overrides[get_current_user] = _auth_as(admin_user)
    try:
        # Search by display_name substring matching the annotator fixture ("Annotator")
        resp = await client.get("/api/v1/admin/users", params={"search": "Annotator"})
        assert resp.status_code == 200
        data = resp.json()
        returned_ids = {u["id"] for u in data}
        assert str(annotator.id) in returned_ids
        # plain_user display_name is "PlainUser" — should not appear
        assert str(plain_user.id) not in returned_ids

        # Search by email substring
        resp2 = await client.get("/api/v1/admin/users", params={"search": "plain@"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        returned_ids2 = {u["id"] for u in data2}
        assert str(plain_user.id) in returned_ids2
        assert str(annotator.id) not in returned_ids2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
