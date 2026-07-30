"""
Seed unit tests. No network — AdminApi is driven by an httpx.MockTransport and
the env-file helpers are pure.

The full seed against a running platform is a manual verification step; see
README.md.
"""

import json
from dataclasses import replace

import httpx
import pytest

from llm_panel.conditions import CONDITION_A, CONDITION_B, CONDITIONS, Bot
from llm_panel.seed import (
    BEGIN_MARKER,
    END_MARKER,
    AdminApi,
    SeedError,
    preflight,
    render_env_block,
    write_env_file,
)

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_preflight_accepts_the_committed_conditions() -> None:
    preflight(CONDITIONS)


def test_preflight_rejects_a_shared_display_name() -> None:
    clash = replace(
        CONDITION_B,
        roster=(*CONDITION_B.roster[:-1], Bot("clash", "Claude Panel", "facilitator")),
    )
    with pytest.raises(SeedError, match="Duplicate display_name"):
        preflight((CONDITION_A, clash))


def test_preflight_rejects_a_leak_in_a_blind_condition() -> None:
    leaky = replace(
        CONDITION_B,
        description="A research forum where language models deliberate.",
    )
    with pytest.raises(SeedError, match="'research'"):
        preflight((leaky,))


def test_preflight_rejects_a_condition_with_no_facilitator() -> None:
    headless = replace(
        CONDITION_A,
        roster=tuple(replace(b, tier="registered") for b in CONDITION_A.roster),
    )
    with pytest.raises(SeedError, match="exactly one facilitator"):
        preflight((headless,))


def test_preflight_rejects_two_facilitators() -> None:
    crowded = replace(
        CONDITION_A,
        roster=tuple(replace(b, tier="facilitator") for b in CONDITION_A.roster),
    )
    with pytest.raises(SeedError, match="exactly one facilitator"):
        preflight((crowded,))


# ---------------------------------------------------------------------------
# AdminApi
# ---------------------------------------------------------------------------


def _api(handler) -> AdminApi:
    return AdminApi(
        "http://platform.test", "admin-token", transport=httpx.MockTransport(handler)
    )


def test_create_community_sets_research_mode_public_and_invite_only() -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(201, json={"slug": sent["slug"], "research_mode": True})

    with _api(handler) as api:
        community, created = api.ensure_community(CONDITION_A)

    assert created is True
    assert community["research_mode"] is True
    assert sent["research_mode"] is True
    # Public so the bots can read the community they post in; invite-only so
    # nobody can join it. research_mode keeps it out of the directory.
    assert sent["is_public"] is True
    assert sent["is_invite_only"] is True
    assert sent["slug"] == CONDITION_A.slug
    assert sent["community_type"] == CONDITION_A.community_type


def test_existing_community_is_read_back_rather_than_failing() -> None:
    """409 is the idempotent path, not an error."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.method} {request.url.path}")
        if request.method == "POST":
            return httpx.Response(409, json={"detail": "already exists"})
        return httpx.Response(
            200, json={"slug": CONDITION_A.slug, "research_mode": True}
        )

    with _api(handler) as api:
        community, created = api.ensure_community(CONDITION_A)

    assert created is False
    assert community["research_mode"] is True
    assert paths == [
        "POST /api/v1/communities",
        f"GET /api/v1/communities/{CONDITION_A.slug}",
    ]


def test_register_reports_created_vs_existing() -> None:
    bot = CONDITION_A.roster[0]
    sent: dict = {}

    def created_handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(201, json={})

    with _api(created_handler) as api:
        assert api.ensure_user(CONDITION_A, bot) is True

    assert sent["supabase_uid"] == "llm-panel-a-claude-panel"
    assert sent["email"] == "a-claude-panel@llm-panel.example"
    assert sent["display_name"] == "Claude Panel"

    with _api(lambda r: httpx.Response(409, json={"detail": "exists"})) as api:
        assert api.ensure_user(CONDITION_A, bot) is False


def test_add_member_sends_email_and_tier() -> None:
    facilitator = CONDITION_A.facilitator()
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["path"] = request.url.path
        sent["body"] = json.loads(request.content)
        return httpx.Response(201, json={})

    with _api(handler) as api:
        api.ensure_member(CONDITION_A, facilitator)

    assert sent["path"] == f"/api/v1/communities/{CONDITION_A.slug}/members"
    assert sent["body"] == {
        "email": CONDITION_A.email(facilitator),
        "tier": "facilitator",
    }


def test_platform_errors_surface_with_the_status_code() -> None:
    from llm_panel.platform_client import PlatformError

    def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Platform admin only."})

    with _api(forbidden) as api, pytest.raises(PlatformError) as exc:
        api.ensure_community(CONDITION_A)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# .env.llm-panel
# ---------------------------------------------------------------------------


def test_env_block_round_trip_preserves_operator_config(tmp_path) -> None:
    """
    The seed reads its config from the same file it writes tokens to. Losing the
    operator's secrets on a re-run would be a nasty way to find that out.
    """
    path = tmp_path / ".env.llm-panel"
    path.write_text(
        "LLM_PANEL_BASE_URL=https://civic-platform-staging.onrender.com\n"
        "SUPABASE_JWT_SECRET=super-secret\n"
    )

    write_env_file(path, {"A_CLAUDE_PANEL_JWT": "token-one"})
    first = path.read_text()
    assert "SUPABASE_JWT_SECRET=super-secret" in first
    assert "A_CLAUDE_PANEL_JWT=token-one" in first

    write_env_file(
        path, {"A_CLAUDE_PANEL_JWT": "token-two", "B_ALVAREZ_JWT": "token-b"}
    )
    second = path.read_text()

    assert "SUPABASE_JWT_SECRET=super-secret" in second
    assert "LLM_PANEL_BASE_URL=https://civic-platform-staging.onrender.com" in second
    assert "token-one" not in second
    assert "A_CLAUDE_PANEL_JWT=token-two" in second
    assert "B_ALVAREZ_JWT=token-b" in second
    # Exactly one managed block, no matter how many times we run.
    assert second.count(BEGIN_MARKER) == 1
    assert second.count(END_MARKER) == 1


def test_env_file_is_created_when_absent_and_is_owner_only(tmp_path) -> None:
    path = tmp_path / ".env.llm-panel"
    write_env_file(path, {"A_CLAUDE_PANEL_JWT": "token"})

    assert path.exists()
    assert "A_CLAUDE_PANEL_JWT=token" in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600


def test_render_env_block_is_delimited() -> None:
    block = render_env_block({"A_CLAUDE_PANEL_JWT": "x"})
    assert block.startswith(BEGIN_MARKER)
    assert block.endswith(END_MARKER)
