"""
Tests for POST /api/v1/proposals/preview

Validates:
- Authenticated user receives rendered HTML
- Unauthenticated request returns 401
- Empty markdown returns empty html string
- Markdown with headings, bold, tables renders expected HTML
"""
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.markdown import render_markdown
from app.main import app
from app.models.community import Community, CommunityType
from app.models.community_membership import CommunityMembership
from app.models.user import User, UserTier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def community(db_session: AsyncSession) -> Community:
    c = Community(
        slug="preview-community",
        name="Preview Community",
        description="Community for preview endpoint tests.",
        community_type=CommunityType.GEOGRAPHIC,
        boundary_desc="Test boundary",
        verification_method="Test verification",
        is_public=True,
        is_invite_only=False,
    )
    db_session.add(c)
    await db_session.commit()
    return c


@pytest_asyncio.fixture
async def registered_user(db_session: AsyncSession, community: Community) -> User:
    u = User(
        supabase_uid="uid-preview-user",
        email="preview-user@example.com",
        display_name="PreviewUser",
        tier=UserTier.REGISTERED,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(CommunityMembership(
        community_id=community.id,
        user_id=u.id,
        tier=UserTier.REGISTERED,
        joined_at=datetime.now(UTC),
    ))
    await db_session.commit()
    return u


def _auth(user: User):
    def _dep():
        return user
    return _dep


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_returns_rendered_html(
    client: AsyncClient,
    registered_user: User,
) -> None:
    """Authenticated user receives HTML rendered from markdown input."""
    app.dependency_overrides[get_current_user] = _auth(registered_user)
    try:
        markdown = "## Summary\n\nThis is a **bold** statement."
        resp = await client.post(
            "/api/v1/proposals/preview",
            json={"markdown": markdown},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "html" in data
        expected = render_markdown(markdown)
        assert data["html"] == expected
        assert "<h2" in data["html"]
        assert "<strong>" in data["html"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_preview_requires_auth(
    client: AsyncClient,
) -> None:
    """Unauthenticated request returns 401."""
    resp = await client.post(
        "/api/v1/proposals/preview",
        json={"markdown": "## Hello"},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_preview_empty_markdown_returns_empty_html(
    client: AsyncClient,
    registered_user: User,
) -> None:
    """Empty markdown string returns empty html."""
    app.dependency_overrides[get_current_user] = _auth(registered_user)
    try:
        resp = await client.post(
            "/api/v1/proposals/preview",
            json={"markdown": ""},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["html"] == ""
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_preview_renders_table(
    client: AsyncClient,
    registered_user: User,
) -> None:
    """Markdown table renders to HTML table elements."""
    app.dependency_overrides[get_current_user] = _auth(registered_user)
    try:
        markdown = "| A | B |\n|---|---|\n| 1 | 2 |"
        resp = await client.post(
            "/api/v1/proposals/preview",
            json={"markdown": markdown},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "<table" in data["html"]
        assert "<th" in data["html"]
        assert "<td" in data["html"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_preview_renders_heading_with_id(
    client: AsyncClient,
    registered_user: User,
) -> None:
    """H2 and H3 headings get deterministic id attributes (used for TOC anchors)."""
    app.dependency_overrides[get_current_user] = _auth(registered_user)
    try:
        markdown = "## Background\n\n### Details"
        resp = await client.post(
            "/api/v1/proposals/preview",
            json={"markdown": markdown},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert 'id="background"' in data["html"]
        assert 'id="details"' in data["html"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_preview_matches_render_markdown_output(
    client: AsyncClient,
    registered_user: User,
) -> None:
    """Preview endpoint output exactly matches core/markdown.py render_markdown()."""
    app.dependency_overrides[get_current_user] = _auth(registered_user)
    try:
        markdown = (
            "## Proposal\n\n"
            "We propose **three** things:\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n\n"
            "See [the wiki](/wiki) for context.\n"
        )
        resp = await client.post(
            "/api/v1/proposals/preview",
            json={"markdown": markdown},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["html"] == render_markdown(markdown)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
