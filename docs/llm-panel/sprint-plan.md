# LLM Panel — Platform Flag, Seeding Layer, and Orchestrator

## Context

A research instrument that runs multi-LLM deliberations through the platform's
own phase-gated infrastructure, then debriefs the models about the process. The
goal is to compare how a phase-gated structure shapes reasoning across framings,
and to generate process feedback that could improve human deliberation too.

Prompt text and survey questions come from the source blueprints
(`llm-panel-prompts.md`, `llm-panel-orchestrator.md` — kept outside the repo) and
are reproduced **verbatim** in `prompts.py`. They are a calibrated instrument,
not a draft. This plan is the authority on API paths, field names, and control
flow.

The panel is deliberately separable: `scripts/llm_panel/` is a peer of
`backend/` with its own `pyproject.toml` and **zero imports from `app.*`**. It
reaches the platform only over HTTP. Extraction to its own repo later is a
directory move plus dropping one column.

**Sprint 1** is the platform flag and seeding layer, ending at a review gate.
**Sprint 2** is the orchestrator.

---

## Platform reference

Facts the implementation depends on. Verified against the current codebase.

**Alembic head:** `b0d77cb5b780`. New migrations set
`down_revision = "b0d77cb5b780"`.

**Auth:** HS256 JWTs verified with `python-jose` against `SUPABASE_JWT_SECRET`.
`aud` and `iss` are not verified; `role == "authenticated"` **is** required
(`core/security.py:92`). The `sub` claim maps to **`User.supabase_uid`**, not
`User.id` (`api/deps.py:46`). A missing user row → 401, no auto-create.

**Required `Community` fields with no default:** `community_type`,
`boundary_desc`, `verification_method` — in addition to `slug`, `name`,
`description`.

**Thread status values are lowercase:** `open`, `deliberating`, `proposing`,
`voting`, `closed`, `archived`.

**Server-side validation limits:** thread title 10–200, prompt 50–2000; post body
10–3000; proposal title 10–200, description **min 50**; phase-advance reason
10–500.

### API map

| Action | Path and payload |
|---|---|
| Create thread | `POST /api/v1/threads` `{community_id, domain_id, title, prompt, context}` — UUIDs, not slugs |
| Create post | `POST /api/v1/posts` `{thread_id, body, parent_id}` |
| Cast signal | `POST /api/v1/signals` `{target_type:"thread", target_id, signal_type, note}` → 200 |
| Create proposal | `POST /api/v1/proposals?thread_id={id}` `{title, description, requested_amount}` — `thread_id` is a query param |
| Cast vote | `POST /api/v1/votes/{proposal_id}` `{choice, rationale}` |
| Advance phase | `PATCH /api/v1/threads/{id}/advance` `{target_status, reason, phase_ends_at}` |
| Read thread | `GET /api/v1/threads/{id}` → `ThreadDetail`, includes `signal_counts` and `my_signal` |
| Read posts | `GET /api/v1/posts/thread/{id}` (nested) or `/flat` |
| Read proposals | `GET /api/v1/proposals/thread/{id}` |
| Read community | `GET /api/v1/communities/{slug}` |
| Create community | `POST /api/v1/communities` — platform admin |
| Add member | `POST /api/v1/communities/{slug}/members` `{email, tier}` — platform admin |
| Register user | `POST /api/v1/auth/register` `{supabase_uid, email, display_name}` — **unauthenticated** |
| Current user | `GET /api/v1/auth/me` → includes `community_memberships` array |

There is **no** per-thread signals list route and no per-user signal
attribution. Aggregate counts come from `ThreadDetail.signal_counts`; a
participant's own signal comes from `ThreadDetail.my_signal`, which requires
reading the thread **with that participant's JWT**.

---

## Experimental conditions

Three framings, each in its own community with its own bot roster. Separation is
required because **display name and community slug are rendered into every
turn** — `render_thread_state` emits `Community: {slug}` and addresses
participants by display name.

| | Community slug | Framing | Roster |
|---|---|---|---|
| **A — Disclosed** | `research-llm-panel` | Research disclosed; co-participants disclosed as LLMs. | `Claude Panel`, `GPT Panel`, `Gemini Panel`, `Facilitator Bot` |
| **B — Blind** | neutral, e.g. `riverside-policy-forum` | Research disclosed; co-participants presented as human community members. | Full names with surnames, e.g. `R. Alvarez`, `J. Chen`, `M. Okafor` |
| **C — Mixed** *(scaffold only)* | `mixed-panel-pilot` | Humans and bots together, bot presence disclosed to humans. | Seeded community + roster; no humans, no prompts |

All three set `research_mode=True`. **Condition B's slug, name, description,
`boundary_desc`, and `verification_method` must be neutral** — no "research",
"LLM", "synthetic", or "experiment". Condition B holds research-framing constant
and varies only co-participant identity.

Each condition gets its own bot user rows; a shared user would carry one
`display_name` across communities and leak condition B.

Condition C is scaffolded as disclosed-mixed only. Blind-mixed involves
deceiving human participants and requires consent and debrief infrastructure
that is out of scope.

---

# Sprint 1 — Platform flag and seeding

### A. Platform changes

Keep this surface minimal — it is the entire extraction cost.

1. **`backend/app/models/community.py`** — add alongside `is_invite_only` (L41):
   ```python
   research_mode: Mapped[bool] = mapped_column(
       Boolean, nullable=False, server_default=text("false"), default=False,
       doc="Synthetic-participant research space. Orchestration scripts may "
           "post on behalf of bot users here. Real communities never set this.",
   )
   ```
   Confirm `Boolean` and `text` are imported from `sqlalchemy`.

2. **Migration** `backend/alembic/versions/<rev>_add_research_mode_to_community.py`
   — **hand-author it; do not use `--autogenerate`.** `models/__init__.py` omits
   `notification.py`, so autogenerate would emit `DROP TABLE notifications`.
   `down_revision = "b0d77cb5b780"`. Add the column with
   `server_default=sa.text("false")`. No RLS statement — CLAUDE.md constraint #11
   covers new tables, not new columns.

3. **`backend/app/schemas/community.py`** — `research_mode: bool = False` on
   `CommunityCreate`; `research_mode: bool` on `CommunityRead`. **Not on
   `CommunityUpdate`** — the flag is set at creation only; toggling is
   unsupported.

4. **`backend/app/api/v1/communities.py`** — three touches:
   - `_build_community_read` (~L83-98): add `research_mode=community.research_mode`.
     This helper constructs `CommunityRead` field-by-field, so adding the schema
     field alone fails validation.
   - `create_community` (L134): pass `research_mode=payload.research_mode`
   - `list_communities` (L106-126): exclude `research_mode == True` from the
     directory for all callers including platform admins (still reachable by slug)

5. **Tests** — `backend/tests/test_research_mode.py`: defaults to `False`;
   settable at creation by platform admin; **not** mutable via
   `PATCH /communities/{slug}`; excluded from `GET /communities`.

### B. `scripts/llm_panel/`

| File | Contents |
|---|---|
| `pyproject.toml` | Own project, package root `llm_panel`. Sprint-1 deps: `pyjwt>=2.8`, `httpx>=0.28`, `python-dotenv`. |
| `README.md` | How to run; the "only thing that talks to the platform" rule; the no-`app.*`-imports rule. |
| `__init__.py` | Empty for Sprint 1. |
| `jwt_util.py` | `generate_bot_jwt(supabase_uid, email, secret, expires_in_days=365)`. `sub` = `supabase_uid`. Must include `role="authenticated"`. HS256. |
| `conditions.py` | The `CONDITIONS` table — one entry per community: slug, name, description, boundary/verification text, roster of `(bot_slug, display_name, tier)`. |
| `platform_client.py` | Community-bound HTTP client. `ResearchModeRequired`. |
| `seed.py` | HTTP-only, idempotent, driven by `CONDITIONS`. |
| `.env.llm-panel.example` | Committed template. |
| `tests/` | Pure unit tests, no network: guard fires on a non-research community; JWT carries the claims `security.py` requires; condition-B text contains no leak terms. |

**`PlatformClient` is bound to one community at construction** and validates
`research_mode` before the first write. It exposes no way to write elsewhere.
The hard guardrail is the platform's own membership gate — bot users hold
`CommunityMembership` only in their own research community, so any misdirected
write 403s server-side.

**Seed sequence**, per condition, all HTTP and idempotent:
1. `POST /api/v1/communities` with the platform-admin JWT, `research_mode=True`,
   `community_type="technical"`. A `general` domain auto-creates
   (`communities.py:163-168`) — use it; no separate `research` domain.
2. Per bot: `POST /api/v1/auth/register` with a deterministic `supabase_uid`
   (e.g. `llm-panel-a-claude-panel`), unique email, condition-appropriate
   display name. 409 → already exists, continue. Emails never reach the models,
   so `@llm-panel.local` is safe in all conditions.
3. `POST /api/v1/communities/{slug}/members` with email + tier — one facilitator
   bot per condition, the rest `registered`.
4. Mint each JWT and write `.env.llm-panel`, namespaced by condition
   (`A_CLAUDE_PANEL_JWT`, `B_ALVAREZ_JWT`, …).
5. Verify each JWT against `GET /api/v1/auth/me`; assert `community_memberships`
   contains the right community at the right tier.

**Communities are created `is_public=True`.** Private communities 404 for
everyone except platform admins — including their own members — so bots could
not read the community they post in. The `research_mode` filter on
`list_communities` keeps them out of the directory, and `is_invite_only=True`
blocks joins.

6. **`.gitignore`** — add `.env.llm-panel` and `scripts/llm_panel/runs/`. The
   existing `*.env` pattern does **not** match a file named `.env.llm-panel`;
   verify with `git check-ignore -v`. Keep `.env.llm-panel.example` committed.

### C. Docs

**Do not copy the source blueprints into the repo.** Their prompt text and code
listings are reproduced by `prompts.py` and the other modules; their API maps and
seed scripts are superseded by this plan. Two copies of a spec is one too many.
Write only what code cannot carry:

- **`docs/llm-panel/design.md`** — one new doc. Port from the blueprints only the
  durable rationale: why the private `reasoning` field does double duty
  (substance + in-the-moment process observations); the calibration notes
  predicting first-run failure modes and what to adjust for each; the design
  choices and known v0.1 limitations. This is what you read *after* a run to
  decide how to iterate the instrument. Add the condition design: three framings,
  what varies, and why disclosure is the independent variable rather than a fixed
  principle.
- **`scripts/llm_panel/README.md`** — operational only: install, seed, run,
  where artifacts land, the no-`app.*`-imports rule.
- **`docs/decisions.md`** — three entries: the `research_mode` flag; the panel's
  repo boundary (HTTP-only, zero platform imports, structured for extraction);
  and the multi-condition design, including why a `research_mode` boolean rather
  than a `research-` slug convention is what allows a neutrally-named blind
  community.
- **`CLAUDE.md`** — narrow exception: the "LLM is not yet integrated" and "no LLM
  posting in threads" rules govern platform features; `research_mode=True`
  communities are a carve-out, and `scripts/llm_panel/` must never import from
  `app.*`.
- **`docs/roadmap.md`** — refresh stale counts (currently says 22 migrations /
  `e8f9a0b1c2d3` / 106 tests; actual head is `b0d77cb5b780`, 29 migration files).

### Sprint 1 verification

If the working container has no `.env` or database, migrations and seeding run in
Codespaces instead. Locally runnable regardless: panel unit tests, ruff, mypy on
changed files.

In Codespaces, **against staging first**:
1. `cd backend && alembic upgrade head`; `alembic current` shows the new revision.
2. `SELECT slug, research_mode FROM communities;` — column present, `false` on
   existing rows.
3. `pytest` — existing suite green plus the new research_mode tests.
4. `uvicorn app.main:app --reload`, then
   `cd scripts/llm_panel && python -m llm_panel.seed`. Expect three communities,
   their bots and memberships, and `.env.llm-panel` written.
5. Re-run the seed → all `[exists]`, no duplicates. Assert no display name or
   email is shared across conditions, and that condition B's community text
   contains none of "research" / "LLM" / "synthetic".
6. `curl -H "Authorization: Bearer $A_CLAUDE_PANEL_JWT" localhost:8000/api/v1/auth/me`
   → 200 with the expected `community_memberships`.
7. A `PlatformClient` bound to `test` raises `ResearchModeRequired`.
8. `GET /api/v1/communities` lists none of the three;
   `GET /api/v1/communities/research-llm-panel` returns `"research_mode": true`.
9. `git status` — `.env.llm-panel` absent, `.env.llm-panel.example` staged.

Commit to `claude/llm-panel-sprint-plan-6zt5ms`. **Review gate — stop here.**

---

# Sprint 2 — Orchestrator

Five modules in `scripts/llm_panel/`: `prompts.py`, `providers.py`, `panel.py`,
`survey.py`, `run.py`, plus `__init__.py` exporting the public API.

**Prerequisite:** `llm-panel-prompts.md` and `llm-panel-orchestrator.md` must be
attached to the session running Sprint 2 — they hold the verbatim prompt text,
the 22 survey questions, and the module structure, none of which are in the repo.
Sprint 1 does not need them.

Provider SDKs (`anthropic`, `openai`, `google-genai`) go in
**`scripts/llm_panel/pyproject.toml`**. Backend's dependencies are untouched.
Imports are rooted at `llm_panel.*`; no `PYTHONPATH` manipulation. Run artifacts
go to `scripts/llm_panel/runs/`.

### Implementation requirements

1. **Phase-case normalization.** Prompt-land uses uppercase phase names; the API
   uses lowercase. Convert in exactly one place. `render_thread_state` gates
   proposal rendering on `state.phase in ("PROPOSING", "VOTING")`, so an
   unnormalized lowercase status silently hides proposals from participants.

2. **`advance_phase` sends `target_status`** (lowercase) alongside `reason`.

3. **VOTING loops over `(participant × unvoted proposal)`** until all pairs are
   covered or a safety cap trips — not a fixed turn count. Each turn, tell the
   participant which proposals it has **not yet** voted on. Votes are immutable
   and the platform 409s on repeats.

4. **Signal state** comes from `ThreadDetail.signal_counts` plus a per-participant
   `my_signal`, which requires reading the thread with that participant's JWT.
   The "no signal" count is `n_participants - sum(counts)`.

5. **Thread creation resolves slugs to UUIDs** — `community_slug` → `community_id`
   via the community read, `general` → `domain_id` via the domains route.

6. **Field names in state assembly:** proposals use `description`. Per-proposal
   vote lists are not returned by `GET /proposals/thread/{id}`; confirm the post
   author field against `PostRead` during implementation. If live vote counts are
   unavailable, make `--show-live-votes` raise rather than render zeros.

7. **Provider adapters** keep the uniform `.complete(system, user) -> dict`
   interface and the three-strategy `_extract_json` with one retry. Use the
   current `google-genai` SDK, not `google-generativeai`. For Anthropic, select
   the first *text* block rather than `content[0]`. Use timezone-aware datetimes.

8. **Guard post length** — skip or pad posts under the platform's 10-char minimum
   rather than letting them 422.

9. **Recall.** `Bot.recall` (`conditions.py`) says what a participant is shown of
   its own prior private `reasoning` when its turn comes round again:
   `none` (default — reason fresh from the public thread each turn) or `own`
   (prior entries replayed as a block in the **user** prompt; the system prompt
   takes no turn-varying content). Recall never crosses participants — nobody
   sees anyone else's reasoning, which is the point of the field being private.
   `run.py --recall {none,own,mixed}`: `none`/`own` force every participant
   uniformly via `Roster.with_recall()`, `mixed` honours the roster. Warn when
   `mixed` is used on a roster where `is_crossed()` is false — recall is then
   confounded with provider identity. See `design.md`.

10. **Rosters.** A condition has several. `run.py --roster <key>` picks one;
    default to the condition's first. A run uses exactly one roster — two
    rosters share a community but must never share a thread. `metadata.json`
    records condition, roster key, naming style, and the resolved
    per-participant recall modes, not just the flags: a run directory has to be
    readable a year later without re-deriving what `mixed` meant that day.

11. **Provider disclosure** is a run-time factor and belongs in
    `build_system_prompt`, alongside the condition text. It is independent of
    the `anonymous` roster, which hides provider identity at the *account*
    level — a display name of `Claude Panel` cannot be un-said by a prompt
    flag, which is why both exist. Sprint 2's leak check on a blind or
    anonymous run must grep the assembled prompt for every provider name.

### Conditions in `prompts.py`

Split `SYSTEM_BASE` into a shared core plus a swappable "WHAT THIS IS" block so
the conditions differ in exactly one auditable place:

- `CONDITION_DISCLOSED` — current text verbatim.
- `CONDITION_BLIND` — keeps the research framing; replaces the "you are a large
  language model, and the other participants are also large language models"
  paragraph with co-participants presented as human community members.
  Everything downstream is untouched.

`build_system_prompt(display_name, n_participants, phase, condition)`.
`run.py` gains `--condition {disclosed,blind}`, records it in `metadata.json`,
and resolves community slug and roster from it. The same `--thread-prompt` must
be usable across conditions.

### Two-stage debrief

`survey.py` takes a `stage` parameter and writes `survey_<slug>_stage1.json` and
`_stage2.json`.

- **Stage 1 — in-frame.** Runs while the blind condition still believes it
  deliberated with humans. Existing questions minus `human_comparison` and the
  AI-facing half of `research_integrity`, both of which presuppose the model
  knows it is not human.
- **Stage 2 — post-reveal.** Discloses the framing, asks the deferred questions,
  and adds a manipulation check: did you suspect any participant was an LLM, at
  what point, and what tipped you off. Without this, a null result in condition B
  is uninterpretable.

Condition A runs both stages with Stage 2's reveal reduced to a no-op, so the
conditions differ in framing only, not in survey design. Existing question ids
stay stable; Stage-2 ids are additive.

### Local models

Add `OpenAICompatibleProvider(base_url=...)` — Ollama, llama.cpp server, vLLM,
and LM Studio all expose OpenAI-compatible endpoints, so a local participant is a
registry entry rather than new code. Local models conform to JSON schemas less
reliably, so the retry path carries more load; consider grammar-constrained
decoding if failure rates are high. Each local participant needs its own seeded
bot user — add it to `CONDITIONS` and re-run the seed.

### Sprint 2 verification

1. Prompt-rendering smoke test, no API calls.
2. One real single-provider call returning a parsed dict.
3. Full run at `--turns-per-phase 2` against staging. Run directory contains
   `metadata.json` (with `condition`), `transcript.json`, per-participant
   `reasoning_*.jsonl`, and `survey_*_stage1.json` / `_stage2.json` covering
   every question id across both stages.
4. Proposals appear in rendered state during PROPOSING.
5. Every participant has voted on every proposal at CLOSED.
6. **Condition-leak check on a blind run:** grep the assembled system prompt and
   rendered thread state for `research-llm-panel`, "LLM", "language model", and
   every condition-A display name. Any hit invalidates the run.
7. Platform audit log shows all events with the research community's
   `community_id` and correct bot attribution.

### Deliberately not built

No run resumption, no cost tracking, round-robin turn-taking only, no LLM-backed
facilitator, naive fixed inter-turn delay. These are v0.1 constraints — see the
first run before changing them. A run is roughly 39 provider calls and low
single-digit dollars.
