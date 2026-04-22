# CLAUDE.md — Civic Power Consortium

This file is read by Claude Code at the start of every session.

## Project Overview

Civic Power Consortium — a nonprofit civic platform converting deliberation
into legitimate collective allocation. No outrage dynamics by design.

**Architecture:** Multi-community. Each community owns its threads, members,
facilitators, domains, and audit trail. The platform is multi-tenant
deliberation infrastructure — the same codebase serves an HOA, a city, a
union local, or a topical group.
**Target:** Web-first (plain HTML/CSS/JS → React migration planned).
**Stage:** MVP — multi-community refactor complete. First real deployment
target: Redlands, CA (`/c/redlands`).
**Dev environment:** GitHub Codespaces (primary). No local tooling assumed.

---

## Current Build Status (as of 2026-04-22)

**What's live and working:**

*Infrastructure*
- Multi-community data model: `Community`, `CommunityMembership` tables
- `platform_role` field on users (user | platform_admin) for platform-level ops
- 16 Alembic migrations (head: `c5d6e7f8a9b0`)
- 58 passing tests

*Pages and routes*
- `/` `/how-it-works` `/quiz` `/signin` `/account` `/wiki` `/wiki/{slug}`
  — unchanged from pre-refactor
- `/c/{slug}` — community home page (public if community.is_public)
- `/c/{slug}/threads` — thread list scoped to community
- `/c/{slug}/thread/{id}` — thread detail
- `/c/{slug}/new-thread` — create thread in community
- `/c/{slug}/audit` — community-scoped audit log (public if community.is_public)
- `/c/{slug}/members` — public member list (display name + tier, no PII)
- `/c/{slug}/admin` — community admin: facilitator requests, member tiers
- `/admin` — platform admin only: community creation, annotator management
- `/audit` — platform-level events only (community_id IS NULL)
- `/threads`, `/thread/{id}`, `/new-thread` — 302 redirect to `/c/test/...`

*Auth and tiers*
- Supabase magic link, JWT with client-side expiry detection
- Community membership is the gate for all deliberative actions
  (not global users.tier — that field is now vestigial)
- All deliberative write actions require `registered` community membership:
  create thread, post, signal, propose, vote, submit amendment
- Phase-advance and moderation require `facilitator` membership in that community
- Facilitator request flow: account page → community admin approval →
  CommunityMembership.tier promoted (not users.tier)

*Deliberation features*
- Signals: 4-type (support/concern/need_info/block), polymorphic targets
  (thread/post/proposal/comment/amendment), one per user per target
- Posts: phase-gated (OPEN/DELIBERATING), soft-delete by facilitator
- Proposals: PROPOSING phase, with versioning, comments, and amendments
- Voting: yes/no/abstain, VOTING phase, immutable, one per user
- Phase-advance controls: facilitator UI, required reason, audit log
- Audit log: append-only, public API, community-scoped + platform-level split

*Wiki and annotations*
- Wiki at `/wiki/{slug}` — global platform resource, not community-scoped
- Inline annotations on wiki articles (annotator capability, endorse/needs_work reactions)

**What is NOT yet built:**

- Real communities seeded in DB — `test` community exists; `redlands`,
  `civic-power-consortium`, `macro-circle` must be created via `/admin`
- Full admin UI for pools and allocations (API routes exist; no admin UI form yet)
- End-to-end test: full thread lifecycle with 3 test users
- Participant tier enforcement (everything at `registered` for now;
  `participant` tier in schema as reserved future state)
- Per-community wiki (deferred to Phase 2)

**What is explicitly deferred:**
- LLM integration (Phase 5 — do not add until Phase 4 deliberation is validated)
- React migration (no npm/build toolchain yet)
- Rate limiting, participant verification web flow, render.yaml
- Personal activity feed (Phase 2)
- Email-bridge contact feature (Phase 2)

---

## Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 (async) + Alembic |
| Database | PostgreSQL 16 (Supabase cloud) |
| Auth | Supabase Auth (magic links + JWT) |
| Frontend | Plain HTML/CSS/JS served from FastAPI |
| Hosting | Render.com (backend + static frontend) |
| Python version | 3.12 |

---

## Project Structure
```
backend/          FastAPI backend
  app/
    models/       SQLAlchemy models (source of truth for data)
      community.py           Community
      community_membership.py  CommunityMembership
      user.py                User (includes platform_role)
      domain.py              Domain (community-scoped via community_id)
      thread.py              Thread (community-scoped via community_id)
      audit.py               AuditLog (community_id nullable)
      pool.py                FundingPool (community-scoped)
      facilitator_request.py FacilitatorRequest (community-scoped)
      post.py, proposal.py, vote.py, signal.py, amendment.py,
      proposal_comment.py, proposal_version.py,
      annotation.py, allocation.py
    schemas/      Pydantic schemas (API input/output)
    api/v1/       Route handlers
      communities.py  Community CRUD, join, members, audit
      admin.py        Platform admin (annotators, user list)
      auth.py         Registration, /me (includes memberships), facilitator request
      threads.py      Community-scoped thread CRUD and phase advance
      posts.py, signals.py, proposals.py, votes.py, amendments.py,
      proposal_comments.py, domains.py, pools.py, allocations.py,
      annotations.py, audit.py
    core/         security.py (JWT), audit.py (log writer)
    db/session.py Async session factory
    static/js/    api.js, nav.js, thread.js, auth.js, utils.js,
                  annotations.js, annotation_ui.js, annotation_anchor.js
    templates/    HTML pages
      community_home.html, community_members.html, community_admin.html
      threads.html, thread.html, new-thread.html, account.html,
      admin.html, audit.html, signin.html, wiki_index.html,
      wiki_article.html, how-it-works.html, quiz.html, index.html
  alembic/        DB migrations (16 total; head: c5d6e7f8a9b0)
  tests/          pytest (58 tests)

docs/             Architecture, roadmap, LLM integration guide, decision log
                  community-model-v0.3.md — multi-community spec (resolved)
index.html        Public landing page (served via GitHub Pages)
```

---

## Dev Commands
```bash
# Install Claude Code (run once in Codespaces)
curl -fsSL https://claude.ai/install.sh | bash

# Backend
cd backend
pip install -e ".[dev]"
cp .env.example .env          # fill in Supabase credentials
alembic upgrade head           # run migrations
uvicorn app.main:app --reload  # dev server at :8000
pytest                         # run tests
ruff check .                   # lint
mypy app --ignore-missing-imports  # type check
```

---

## Key Architectural Constraints

1. **Audit log is append-only.** Never write UPDATE/DELETE on `audit_logs`.
   Use `core/audit.log_event()` only. Signature:
   `log_event(db, event_type, target_type, target_id, payload,
   actor_id=None, community_id=None)`.
   Pass `community_id` for every community-scoped action. The audit log
   is a capture detector, not just an accountability surface.

2. **Thread phase transitions are strict.** Use `thread.can_advance_to()`.
   Never update `Thread.status` directly — always go through the API route
   which validates the state machine and writes to audit log.

3. **Votes are immutable.** Once cast, a vote cannot be changed.
   The DB has a unique constraint on (proposal_id, voter_id).

4. **Reactions must never determine display order, visibility, or prominence.**
   Chronological ordering is the only permitted sort for any content feed.
   Reaction counts may be displayed but must not be used as sort keys,
   filters, or ranking inputs.

5. **Phase gates are enforced server-side.** Never trust the client to
   enforce which actions are allowed in which phase.

6. **LLM is not yet integrated.** Do not add LLM calls until Phase 4
   of the roadmap. See `docs/llm-integration.md`.

7. **api.js must stay framework-agnostic.** No DOM manipulation in api.js —
   only fetch() calls that return data. This file must survive unchanged
   when the frontend migrates to React.

8. **Community membership is the authorization gate for deliberative actions.**
   All routes that create, modify, or moderate community content must check
   `CommunityMembership.tier` for the relevant community — never `users.tier`.
   Use `community_tier_required(min_tier)` from `api/deps.py`.
   `users.tier` is vestigial and will be dropped in a future cleanup migration.

9. **Two distinct admin roles — do not conflate them.**
   - `PlatformAdminUser` (from deps.py): `user.platform_role == 'platform_admin'`.
     Gates: create/manage communities, grant annotator capability, list all users.
   - `CommunityAdminUser` (from deps.py): user has `facilitator` or `admin`
     `CommunityMembership.tier` in the target community. PlatformAdminUser
     also satisfies this. Gates: approve facilitator requests, manage community
     member tiers.
   Do not use the old `AdminUser` dep for new routes — it checks `users.tier`
   and is only kept for backward compatibility in existing routes being migrated.

10. **Community scope must be passed to every audit event.**
    Every `log_event()` call inside a community-scoped route must pass
    `community_id=thread.community_id` (or the equivalent). Platform-level
    events (community creation, annotator grants) pass `community_id=None`.

---

## Conventions

- **Python:** Prefer `async def` for all DB-touching code.
- **Models:** Use SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style.
- **Schemas:** Pydantic v2 `model_config = ConfigDict(from_attributes=True)`.
- **Routes:** Type-annotate all parameters. Use `Annotated[X, Depends(Y)]`.
- **Audit:** Call `core.audit.log_event()` inside the same transaction as the
  action. Always pass `community_id` for community-scoped actions.
- **HTML/JS:** Write one JavaScript function per UI component. Keep DOM
  manipulation out of api.js.
- **Community resolution:** Routes that need the community resolve it via
  `get_community(slug, db)` from `api/deps.py`. The community is the
  slug in the URL path for `/c/{slug}/...` routes, or the `community_id`
  field on the relevant model (thread, domain, pool) for nested resources.

---

## What NOT to Do

- Do NOT add crypto, tokens, or blockchain. Explicitly excluded from MVP.
- Do NOT allow the LLM to post in threads. It is read-only.
- Do NOT skip the phase gate in any route, even "just for testing."
- Do NOT add upvotes, downvotes, or engagement metrics on posts.
- Do NOT use reaction counts to sort, filter, rank, boost, or bury any content.
  Chronological order only. Reactions are editorial signal, not display signal.
- Do NOT store PII in the audit log payload.
- Do NOT commit `.env` files.
- Do NOT use `git push --force` on `main`.
- Do NOT add React, npm, or any build toolchain to the frontend yet.
  Plain HTML/CSS/JS only until the migration is explicitly planned.
- Do NOT reference or restore anything from the archived mobile/ scaffold.
- Do NOT check `users.tier` to gate community-scoped actions. Use
  `CommunityMembership.tier` via `community_tier_required()`. The global
  tier field is vestigial.
- Do NOT use the old global `AdminUser` dependency for new routes. Use
  `PlatformAdminUser` for platform-level operations or `CommunityAdminUser`
  for community-level operations.
- Do NOT create new page routes for community content outside the
  `/c/{slug}/...` URL namespace. The `/c/` prefix is load-bearing —
  it prevents slug collisions with top-level routes.
- Do NOT scope the wiki or annotation system to communities. The wiki is
  a global platform resource at `/wiki/...`. Per-community wikis are a
  Phase 2 feature that has not been designed yet.

---

## Hosting Setup (Render)

1. Connect GitHub repo to Render
2. New Web Service → Python → Build command: `pip install -e .`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set environment variables from `.env.example`
5. `DEBUG=false` in production

---

## Testing Philosophy

Tests should verify **legitimacy rules**, not just CRUD:
- Phase gate enforcement (can't vote while deliberating)
- Audit log population (every action leaves a record with community_id)
- Vote immutability (can't vote twice)
- State machine correctness (can't skip phases)
- Community membership gates (non-members can't write; cross-community
  facilitators can't advance phases in another community's threads)
- Audit log reconstructability (can you rebuild a decision from the log alone?)

See `backend/tests/test_threads.py` and `backend/tests/test_communities.py`
for examples.
