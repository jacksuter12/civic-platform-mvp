"""
The only thing in this package that talks to the platform.

`PlatformClient` is bound to exactly one community at construction and refuses
to write until it has confirmed that community has `research_mode=True`. There
is no method that takes a community — the binding is not a default, it is the
whole object.

That guard is a tripwire, not a security boundary. The real guardrail is the
platform's own membership gate: a bot user holds `CommunityMembership` only in
its own research community, so a misdirected write 403s server-side no matter
what this client does. The guard exists to fail loudly at the top of a run
instead of quietly at turn 14.

No imports from `app.*`. Ever. HTTP is the entire interface.
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"
DEFAULT_TIMEOUT = 30.0


class PlatformError(RuntimeError):
    """A platform request failed, or returned something we can't work with."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ResearchModeRequired(PlatformError):
    """
    Refused to write: the bound community is not a research space.

    Raised before the request is sent. If you are seeing this against a
    community you just created, the seed did not pass `research_mode=True`.
    """


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Turn a non-2xx into a PlatformError carrying the platform's own detail."""
    if response.is_success:
        return
    body = response.text
    raise PlatformError(
        f"{context} failed: HTTP {response.status_code} — {body[:500]}",
        status_code=response.status_code,
        body=body,
    )


class PlatformClient:
    """
    HTTP client for one bot user acting in one research community.

    Reads are unguarded — a bot must be able to read the community it posts in.
    Every write goes through `_write`, which asserts research mode first.
    Sprint 2's thread/post/signal/proposal/vote methods are built on `_write`;
    Sprint 1 needs only the binding, the guard, and `me()`.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        community_slug: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError(
                "token is required — mint one with jwt_util.generate_bot_jwt"
            )
        if not community_slug:
            raise ValueError(
                "community_slug is required — the client binds to one community"
            )

        self.base_url = base_url.rstrip("/")
        self.community_slug = community_slug
        self._http = httpx.Client(
            base_url=f"{self.base_url}{API_PREFIX}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )
        self._community: dict[str, Any] | None = None

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PlatformClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- the binding --------------------------------------------------------

    @property
    def community(self) -> dict[str, Any]:
        """The bound community, fetched once and cached. Guarded on first load."""
        if self._community is None:
            self._community = self._load_community()
        return self._community

    @property
    def community_id(self) -> str:
        return str(self.community["id"])

    def _load_community(self) -> dict[str, Any]:
        response = self._http.get(f"/communities/{self.community_slug}")
        if response.status_code == 404:
            raise PlatformError(
                f"Community {self.community_slug!r} not found, or not visible to this "
                "token. Research communities are created is_public=True precisely so "
                "their own members can read them — check the seed.",
                status_code=404,
                body=response.text,
            )
        raise_for_status(response, f"GET /communities/{self.community_slug}")
        community: dict[str, Any] = response.json()

        if not community.get("research_mode"):
            raise ResearchModeRequired(
                f"Community {self.community_slug!r} does not have research_mode set. "
                "The panel only ever writes into synthetic-participant spaces."
            )
        return community

    def assert_research_mode(self) -> None:
        """
        Force the guard now rather than at the first write. Cheap to call; the
        community read is cached after the first hit.
        """
        _ = self.community

    # -- requests -----------------------------------------------------------

    def _read(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._http.get(path, params=params)
        raise_for_status(response, f"GET {path}")
        return response.json()

    def _write(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        self.assert_research_mode()
        response = self._http.request(method, path, json=json, params=params)
        raise_for_status(response, f"{method} {path}")
        if not response.content:
            return None
        return response.json()

    # -- Sprint 1 surface ---------------------------------------------------

    def me(self) -> dict[str, Any]:
        """The bot's own user record, including `community_memberships`."""
        result: dict[str, Any] = self._read("/auth/me")
        return result

    def membership_tier(self) -> str | None:
        """This bot's tier in the bound community, or None if it is not a member."""
        for membership in self.me().get("community_memberships", []):
            if membership.get("community_slug") == self.community_slug:
                tier: str = membership["tier"]
                return tier
        return None
