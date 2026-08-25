"""
Seed the research communities, their bot users, and their JWTs.

HTTP only, idempotent, driven entirely by `conditions.CONDITIONS`. Re-running
is the normal case: every step either creates the thing or reports `[exists]`.

    cd scripts/llm_panel
    cp .env.llm-panel.example .env.llm-panel   # fill in the two secrets
    python -m llm_panel.seed

Per condition:
  1. POST /communities                     research_mode=True, is_public=True,
                                           is_invite_only=True. A `general`
                                           domain auto-creates — the panel uses it.
  2. POST /auth/register                   one bot user per roster entry,
                                           deterministic supabase_uid
  3. POST /admin/users/synthetic           label the account as a bot, so every
                                           human who reads it knows
  4. POST /communities/{slug}/members      one facilitator, the rest registered
  5. mint a JWT per bot, write .env.llm-panel
  6. GET /auth/me with each JWT            assert the membership actually landed
                                           and the synthetic label stuck

Communities are created public on purpose. A private community 404s for
everyone except platform admins — *including its own members* — so the bots
could not read the community they post in. `research_mode` keeps them out of
the public directory and `is_invite_only` blocks joins; neither depends on
`is_public`.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from llm_panel.conditions import (
    CONDITIONS,
    NAMING_STYLES,
    PROVIDERS,
    RECALL_MODES,
    Bot,
    Condition,
    Roster,
    condition_by_key,
    find_leak_terms,
)
from llm_panel.jwt_util import generate_bot_jwt
from llm_panel.platform_client import PlatformClient, PlatformError, raise_for_status

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PACKAGE_ROOT / ".env.llm-panel"

DEFAULT_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

BEGIN_MARKER = "# --- BEGIN llm_panel.seed generated bot tokens ---"
END_MARKER = "# --- END llm_panel.seed generated bot tokens ---"


class SeedError(RuntimeError):
    """The seed cannot proceed. Message is operator-facing."""


# ---------------------------------------------------------------------------
# Preflight — cheap assertions that run before we touch the platform
# ---------------------------------------------------------------------------


def preflight(conditions: tuple[Condition, ...]) -> None:
    """
    Fail before any network call if the condition table is internally broken.

    These duplicate tests/test_conditions.py deliberately: the tests protect the
    committed table, this protects whatever table is actually in the file when
    someone runs the seed at 2am.
    """
    problems: list[str] = []

    for condition in conditions:
        for roster in condition.rosters:
            try:
                roster.facilitator()
            except ValueError as exc:
                problems.append(f"Condition {condition.key}: {exc}")
            if roster.naming not in NAMING_STYLES:
                problems.append(
                    f"Roster {condition.key}/{roster.key} has unknown naming "
                    f"style {roster.naming!r}"
                )
            for bot in roster.bots:
                if bot.provider not in PROVIDERS:
                    problems.append(
                        f"Bot {bot.bot_slug!r} has unknown provider "
                        f"{bot.provider!r}"
                    )
                if bot.recall not in RECALL_MODES:
                    problems.append(
                        f"Bot {bot.bot_slug!r} has unknown recall mode "
                        f"{bot.recall!r}"
                    )

        if condition.blind:
            for term, text in find_leak_terms(condition):
                problems.append(
                    f"Condition {condition.key} is blind but its visible text "
                    f"contains {term!r}: {text!r}"
                )

    # A display name or email shared across conditions would link two rosters
    # and, for a blind condition, give the whole thing away. bot_slug has to be
    # unique condition-wide too, since the env var name is derived from it alone.
    for field, values in (
        ("slug", [c.slug for c in conditions]),
        ("display_name", [b.display_name for c in conditions for b in c.all_bots()]),
        ("email", [c.email(b) for c in conditions for b in c.all_bots()]),
        (
            "supabase_uid",
            [c.supabase_uid(b) for c in conditions for b in c.all_bots()],
        ),
        ("env_var", [c.env_var(b) for c in conditions for b in c.all_bots()]),
    ):
        duplicates = [value for value, count in Counter(values).items() if count > 1]
        if duplicates:
            problems.append(f"Duplicate {field} across conditions: {duplicates}")

    if problems:
        raise SeedError("Condition table is invalid:\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------------
# Admin-authenticated platform calls
# ---------------------------------------------------------------------------


class AdminApi:
    """
    Platform-admin HTTP calls the seed needs. Not a `PlatformClient` — creating
    a community and registering users are platform-level, not community-bound,
    so they deliberately live outside the community-bound client.
    """

    def __init__(
        self,
        base_url: str,
        admin_token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}{API_PREFIX}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AdminApi:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def ensure_community(self, condition: Condition) -> tuple[dict[str, Any], bool]:
        """Returns (community, created)."""
        response = self._http.post(
            "/communities",
            json={
                "slug": condition.slug,
                "name": condition.name,
                "description": condition.description,
                "community_type": condition.community_type,
                "boundary_desc": condition.boundary_desc,
                "verification_method": condition.verification_method,
                "is_public": True,
                "is_invite_only": True,
                "research_mode": True,
            },
        )
        if response.status_code == 409:
            return self.get_community(condition.slug), False
        raise_for_status(response, f"POST /communities ({condition.slug})")
        community: dict[str, Any] = response.json()
        return community, True

    def get_community(self, slug: str) -> dict[str, Any]:
        response = self._http.get(f"/communities/{slug}")
        raise_for_status(response, f"GET /communities/{slug}")
        community: dict[str, Any] = response.json()
        return community

    def ensure_user(self, condition: Condition, bot: Bot) -> bool:
        """Register the bot user. True if created, False if it already existed."""
        response = self._http.post(
            "/auth/register",
            json={
                "supabase_uid": condition.supabase_uid(bot),
                "email": condition.email(bot),
                "display_name": bot.display_name,
            },
        )
        if response.status_code == 409:
            return False
        raise_for_status(response, f"POST /auth/register ({condition.email(bot)})")
        return True

    def ensure_synthetic(self, condition: Condition, bot: Bot) -> None:
        """
        Mark the account as software-operated, so every human who reads it knows.

        Platform-admin only and idempotent on the server. Not settable at
        registration: `POST /auth/register` is unauthenticated, so a
        self-asserted label would be worth nothing.

        The models never see this flag — it is not rendered into any turn. The
        blind condition lives in prompt assembly, not in hidden platform state.
        """
        response = self._http.post(
            "/admin/users/synthetic",
            json={
                "email": condition.email(bot),
                "is_synthetic": True,
                "reason": f"LLM panel bot, condition {condition.key}",
            },
        )
        raise_for_status(
            response, f"POST /admin/users/synthetic ({condition.email(bot)})"
        )

    def ensure_member(self, condition: Condition, bot: Bot) -> None:
        """
        Add or re-tier the bot's membership. The platform route upserts, so this
        is idempotent and also repairs a tier that drifted.
        """
        response = self._http.post(
            f"/communities/{condition.slug}/members",
            json={"email": condition.email(bot), "tier": bot.tier},
        )
        raise_for_status(
            response, f"POST /communities/{condition.slug}/members ({bot.bot_slug})"
        )


# ---------------------------------------------------------------------------
# .env.llm-panel
# ---------------------------------------------------------------------------


def render_env_block(tokens: dict[str, str]) -> str:
    lines = [BEGIN_MARKER, "# Regenerated on every seed run. Do not edit by hand."]
    lines.extend(f"{name}={token}" for name, token in tokens.items())
    lines.append(END_MARKER)
    return "\n".join(lines)


def write_env_file(path: Path, tokens: dict[str, str]) -> None:
    """
    Replace the generated block in `path`, preserving everything the operator
    wrote around it (the base URL and secrets live in the same file).
    """
    existing = path.read_text() if path.exists() else ""
    kept: list[str] = []
    inside = False
    for line in existing.splitlines():
        if line.strip() == BEGIN_MARKER:
            inside = True
            continue
        if line.strip() == END_MARKER:
            inside = False
            continue
        if not inside:
            kept.append(line)

    body = "\n".join(kept).rstrip()
    parts = [body, ""] if body else []
    parts.append(render_env_block(tokens))
    path.write_text("\n".join(parts) + "\n")
    # Long-lived bearer tokens — keep them off other users' eyes.
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def seed_condition(
    api: AdminApi,
    condition: Condition,
    *,
    base_url: str,
    jwt_secret: str,
    rosters: tuple[Roster, ...] | None = None,
    verify: bool = True,
) -> dict[str, str]:
    """
    Seed one condition end to end. Returns the env-var → JWT mapping.

    `rosters` defaults to every roster in the condition. Pass a subset to
    create only the accounts a planned run needs — each roster is real accounts
    on a real platform, so seeding all of them when you will use one is just
    more rows in the public audit log.
    """
    rosters = rosters if rosters is not None else condition.rosters
    print(f"\n[{condition.key}] {condition.label} — /c/{condition.slug}")

    community, created = api.ensure_community(condition)
    print(f"  community  {'[created]' if created else '[exists] '} {condition.slug}")
    if not community.get("research_mode"):
        raise SeedError(
            f"Community {condition.slug!r} exists but research_mode is not set. "
            "The flag is creation-only and cannot be patched on — the community "
            "must be recreated under a new slug."
        )

    tokens: dict[str, str] = {}
    for roster in rosters:
        crossed = " crossed" if roster.is_crossed() else ""
        print(f"  roster     {roster.key} ({roster.naming}{crossed})")

        for bot in roster.bots:
            user_created = api.ensure_user(condition, bot)
            api.ensure_synthetic(condition, bot)
            api.ensure_member(condition, bot)
            tokens[condition.env_var(bot)] = generate_bot_jwt(
                supabase_uid=condition.supabase_uid(bot),
                email=condition.email(bot),
                secret=jwt_secret,
            )
            print(
                f"    bot      {'[created]' if user_created else '[exists] '} "
                f"{bot.display_name:<20} {bot.provider:<10} {bot.tier:<12} "
                f"recall={bot.recall:<5} → {condition.env_var(bot)}"
            )

        if verify:
            for bot in roster.bots:
                token = tokens[condition.env_var(bot)]
                with PlatformClient(base_url, token, condition.slug) as client:
                    tier = client.membership_tier()
                    me = client.me()
                if tier != bot.tier:
                    raise SeedError(
                        f"Verification failed for {bot.display_name}: expected tier "
                        f"{bot.tier!r} in {condition.slug!r}, got {tier!r}"
                    )
                if not me.get("is_synthetic"):
                    raise SeedError(
                        f"Verification failed for {bot.display_name}: the account is "
                        "not labelled synthetic. Humans would read it as a person. "
                        "Check that the platform is migrated past m6f7g8h9i0j1."
                    )
            print(
                f"    verified [ok]      {len(roster.bots)} tokens against "
                "/auth/me, all labelled Bot"
            )

    return tokens


def describe_table() -> str:
    """
    The whole design, printable. Answers "what can I actually run?" without a
    network call or a trip through the source.
    """
    lines: list[str] = []
    for condition in CONDITIONS:
        blind = "  [blind — visible text must stay neutral]" if condition.blind else ""
        lines.append(
            f"\n[{condition.key}] {condition.label} — /c/{condition.slug}{blind}"
        )
        for roster in condition.rosters:
            crossed = "crossed" if roster.is_crossed() else "not crossed"
            counts = ", ".join(
                f"{provider} x{n}"
                for provider, n in sorted(roster.provider_counts().items())
            )
            lines.append(
                f"  {roster.key:<10} naming={roster.naming:<10} "
                f"{len(roster.participants())} participants ({counts}) — {crossed}"
            )
            lines.append(f"             {roster.description}")
    lines.append(
        "\n'crossed' means recall is balanced within every provider, which is "
        "what\nmakes a mixed-recall run interpretable. Uniform runs "
        "(--recall none|own) do\nnot need it."
    )
    return "\n".join(lines)


def _select_rosters(
    condition: Condition, roster_keys: tuple[str, ...] | None
) -> tuple[Roster, ...]:
    """
    Rosters to seed for this condition. `None` means all of them; otherwise
    keep the named ones, silently skipping keys this condition does not have
    so `--roster crossed` across all conditions does the obvious thing.
    """
    if roster_keys is None:
        return condition.rosters
    return tuple(r for r in condition.rosters if r.key in roster_keys)


def run(
    base_url: str,
    admin_token: str,
    jwt_secret: str,
    *,
    conditions: tuple[Condition, ...] = CONDITIONS,
    roster_keys: tuple[str, ...] | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
    verify: bool = True,
) -> dict[str, str]:
    # Preflight the whole table, not just the selected slice: a duplicate
    # display name between a roster you are seeding and one you are not is
    # still a collision waiting to happen.
    preflight(CONDITIONS)

    tokens: dict[str, str] = {}
    with AdminApi(base_url, admin_token) as api:
        for condition in conditions:
            rosters = _select_rosters(condition, roster_keys)
            if not rosters:
                continue
            tokens.update(
                seed_condition(
                    api,
                    condition,
                    base_url=base_url,
                    jwt_secret=jwt_secret,
                    rosters=rosters,
                    verify=verify,
                )
            )

    write_env_file(env_file, tokens)
    print(f"\nWrote {len(tokens)} tokens to {env_file}")
    return tokens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_panel.seed",
        description="Seed the LLM panel's research communities, bots, and tokens.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"Platform base URL (env LLM_PANEL_BASE_URL, default {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--condition",
        action="append",
        metavar="KEY",
        help="Seed only these conditions (A, B, C). Repeatable. Default: all.",
    )
    parser.add_argument(
        "--roster",
        action="append",
        metavar="KEY",
        help=(
            "Seed only these rosters (named, crossed, anonymous, residents, "
            "disclosed). Repeatable. Default: all. Each roster is real accounts "
            "on a real platform — seed what you will actually run."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the condition and roster table, then exit. No network.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Where to read config and write tokens (default {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the GET /auth/me check on each minted token.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print(describe_table())
        return 0

    # Real environment variables win over the file.
    load_dotenv(args.env_file, override=False)

    base_url = args.base_url or os.getenv("LLM_PANEL_BASE_URL") or DEFAULT_BASE_URL
    admin_token = os.getenv("LLM_PANEL_ADMIN_JWT", "")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")

    missing = [
        name
        for name, value in (
            ("LLM_PANEL_ADMIN_JWT", admin_token),
            ("SUPABASE_JWT_SECRET", jwt_secret),
        )
        if not value
    ]
    if missing:
        print(
            f"Missing required config: {', '.join(missing)}.\n"
            f"Copy .env.llm-panel.example to {args.env_file} and fill it in.",
            file=sys.stderr,
        )
        return 2

    if args.condition:
        conditions = tuple(condition_by_key(key) for key in args.condition)
    else:
        conditions = CONDITIONS

    try:
        run(
            base_url,
            admin_token,
            jwt_secret,
            conditions=conditions,
            roster_keys=tuple(args.roster) if args.roster else None,
            env_file=args.env_file,
            verify=not args.no_verify,
        )
    except (SeedError, PlatformError, KeyError) as exc:
        print(f"\nSeed failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
