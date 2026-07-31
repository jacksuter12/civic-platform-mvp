"""
PlatformClient guard tests. No network — every request is answered by an
httpx.MockTransport so these run anywhere.
"""

import httpx
import pytest

from llm_panel.platform_client import (
    PlatformClient,
    PlatformError,
    ResearchModeRequired,
)

BASE_URL = "http://platform.test"
TOKEN = "not-a-real-token"


def _community(slug: str, research_mode: bool) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "research_mode": research_mode,
        "is_public": True,
    }


def _transport(routes: dict[str, httpx.Response], recorder: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.append((request.method, request.url.path))
        for path, response in routes.items():
            if request.url.path.endswith(path):
                return response
        return httpx.Response(404, json={"detail": "Not found"})

    return httpx.MockTransport(handler)


def _client(
    slug: str, routes: dict[str, httpx.Response], recorder=None
) -> PlatformClient:
    return PlatformClient(
        BASE_URL, TOKEN, slug, transport=_transport(routes, recorder)
    )


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_guard_fires_on_a_non_research_community() -> None:
    """A client bound to `test` — an ordinary community — must refuse."""
    routes = {"/communities/test": httpx.Response(200, json=_community("test", False))}
    with _client("test", routes) as client, pytest.raises(ResearchModeRequired):
        client.assert_research_mode()


def test_guard_passes_on_a_research_community() -> None:
    slug = "research-llm-panel"
    routes = {f"/communities/{slug}": httpx.Response(200, json=_community(slug, True))}
    with _client(slug, routes) as client:
        client.assert_research_mode()
        assert client.community_id == "11111111-1111-1111-1111-111111111111"


def test_writes_are_blocked_before_the_request_is_sent() -> None:
    """
    The guard runs first. A write against a non-research community must never
    reach the platform at all.
    """
    sent: list[tuple[str, str]] = []
    routes = {"/communities/test": httpx.Response(200, json=_community("test", False))}
    with _client("test", routes, sent) as client, pytest.raises(ResearchModeRequired):
        client._write("POST", "/posts", json={"thread_id": "x", "body": "hello"})

    assert ("POST", "/posts") not in sent


def test_missing_community_is_a_platform_error_not_a_guard_failure() -> None:
    """
    A private research community 404s for its own members, which looks exactly
    like a missing one. The error message has to say so.
    """
    client = _client("research-llm-panel", {})
    with client, pytest.raises(PlatformError) as exc:
        client.assert_research_mode()
    assert exc.value.status_code == 404
    assert "is_public" in str(exc.value)
    assert not isinstance(exc.value, ResearchModeRequired)


def test_community_is_fetched_once_and_cached() -> None:
    slug = "research-llm-panel"
    sent: list[tuple[str, str]] = []
    routes = {f"/communities/{slug}": httpx.Response(200, json=_community(slug, True))}
    with _client(slug, routes, sent) as client:
        client.assert_research_mode()
        client.assert_research_mode()
        _ = client.community_id

    assert sum(1 for method, _path in sent if method == "GET") == 1


def test_research_mode_required_is_a_platform_error() -> None:
    """Callers that catch PlatformError must also catch the guard failure."""
    assert issubclass(ResearchModeRequired, PlatformError)


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------


def test_client_requires_a_token_and_a_community() -> None:
    with pytest.raises(ValueError):
        PlatformClient(BASE_URL, "", "research-llm-panel")
    with pytest.raises(ValueError):
        PlatformClient(BASE_URL, TOKEN, "")


def test_requests_are_sent_under_the_api_prefix_with_the_bearer_token() -> None:
    slug = "research-llm-panel"
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_community(slug, True))

    client = PlatformClient(
        BASE_URL, TOKEN, slug, transport=httpx.MockTransport(handler)
    )
    with client:
        client.assert_research_mode()

    assert seen["path"] == f"/api/v1/communities/{slug}"
    assert seen["auth"] == f"Bearer {TOKEN}"


# ---------------------------------------------------------------------------
# Membership readback — what the seed verifies each token with
# ---------------------------------------------------------------------------


def test_membership_tier_reads_the_bound_community_only() -> None:
    slug = "research-llm-panel"
    routes = {
        f"/communities/{slug}": httpx.Response(200, json=_community(slug, True)),
        "/auth/me": httpx.Response(
            200,
            json={
                "id": "22222222-2222-2222-2222-222222222222",
                "display_name": "Claude Panel",
                "community_memberships": [
                    {
                        "community_slug": "somewhere-else",
                        "community_name": "Somewhere Else",
                        "tier": "admin",
                    },
                    {
                        "community_slug": slug,
                        "community_name": "LLM Panel",
                        "tier": "facilitator",
                    },
                ],
            },
        ),
    }
    with _client(slug, routes) as client:
        assert client.membership_tier() == "facilitator"


def test_membership_tier_is_none_when_the_bot_is_not_a_member() -> None:
    slug = "research-llm-panel"
    routes = {
        f"/communities/{slug}": httpx.Response(200, json=_community(slug, True)),
        "/auth/me": httpx.Response(200, json={"community_memberships": []}),
    }
    with _client(slug, routes) as client:
        assert client.membership_tier() is None


def test_platform_error_carries_status_and_body() -> None:
    slug = "research-llm-panel"
    routes = {
        f"/communities/{slug}": httpx.Response(200, json=_community(slug, True)),
        "/auth/me": httpx.Response(401, json={"detail": "User not registered."}),
    }
    with _client(slug, routes) as client, pytest.raises(PlatformError) as exc:
        client.me()
    assert exc.value.status_code == 401
    assert "User not registered." in str(exc.value)
