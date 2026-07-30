# llm_panel

A research instrument that runs multi-LLM deliberations through the civic
platform's own phase-gated infrastructure, then debriefs the models about the
process.

Design rationale, condition design, and known limitations live in
[`docs/llm-panel/design.md`](../../docs/llm-panel/design.md). This file is
operational only.

## The rule

**Nothing in this package may import from `app.*`.** The panel is a peer of
`backend/`, not a part of it. It reaches the platform over HTTP and nothing
else — `llm_panel/platform_client.py` is the only module that talks to it at
all. Extracting the panel to its own repo should be a directory move.

`tests/test_no_app_imports.py` enforces this. If it fails, the fix is a route,
not an import.

## Install

Its own project, with its own dependencies. Backend requirements are untouched.

```bash
cd scripts/llm_panel
pip install -e ".[dev]"
```

## Seed

Creates the research communities, their bot users and memberships, and the
long-lived JWTs each bot authenticates with. HTTP only, and idempotent — every
step reports `[created]` or `[exists]`.

```bash
cp .env.llm-panel.example .env.llm-panel   # fill in the two secrets
python -m llm_panel.seed
```

`.env.llm-panel` needs:

| Variable | What it is |
|---|---|
| `LLM_PANEL_BASE_URL` | Where the platform is running. Staging first. |
| `LLM_PANEL_ADMIN_JWT` | A platform-admin token. Communities and memberships are admin-gated. |
| `SUPABASE_JWT_SECRET` | The backend's own secret, for the environment you are seeding. Bot users never touch Supabase Auth, so the panel signs their tokens itself. |

Options:

```bash
python -m llm_panel.seed --condition A --condition B   # subset
python -m llm_panel.seed --base-url https://civic-platform-staging.onrender.com
python -m llm_panel.seed --no-verify                   # skip the /auth/me readback
```

The seed rewrites a delimited block at the bottom of `.env.llm-panel` with one
token per bot (`A_CLAUDE_PANEL_JWT`, `B_ALVAREZ_JWT`, …). Everything you wrote
above that block is preserved, so config and tokens share one file. The file is
gitignored and written `0600`; `.env.llm-panel.example` is the committed
template.

Staging and production have different `SUPABASE_JWT_SECRET` values. A token
minted against one 401s against the other — re-run the seed after switching
environments.

## Conditions

Three framings, each with its own community and its own bot roster
(`llm_panel/conditions.py`):

| | Community | Framing |
|---|---|---|
| **A — disclosed** | `research-llm-panel` | Research disclosed; co-participants disclosed as LLMs. |
| **B — blind** | `riverside-policy-forum` | Research disclosed; co-participants presented as human community members. |
| **C — mixed** | `mixed-panel-pilot` | Scaffold only — seeded community and roster, no prompts. |

Condition B's community text and display names must never contain "research",
"LLM", "synthetic", or "experiment". `seed.preflight()` refuses to run if they
do, and `tests/test_conditions.py` fails if the committed table drifts. A leak
here does not raise anything at runtime — the run completes and the data is
quietly worthless.

Rosters must not share a display name, email, `supabase_uid`, or token env var
across conditions. Same reason.

## Prerequisites on the platform side

- The target environment is migrated past `k5e6f7g8h9i0`, which adds
  `communities.research_mode`.
- The account behind `LLM_PANEL_ADMIN_JWT` has `platform_role='platform_admin'`.

Research communities are created `is_public=True` deliberately: a private
community 404s for everyone but platform admins, *including its own members*,
so the bots could not read the community they post in. `research_mode` keeps
them out of the public directory and `is_invite_only=True` blocks joins.

## Tests

Pure unit tests. No network, no database, no running platform.

```bash
pytest
ruff check .
mypy llm_panel --ignore-missing-imports
```

## Run a deliberation

Sprint 2. `python -m llm_panel.run` and the provider adapters do not exist yet.
Run artifacts will land in `scripts/llm_panel/runs/` (gitignored).
