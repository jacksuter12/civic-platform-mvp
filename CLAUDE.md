# CLAUDE.md — Civic Power Consortium

This file is read by Claude Code at the start of every session.

## Project Overview

Civic Power Consortium — a nonprofit civic platform converting deliberation
into legitimate collective allocation. No outrage dynamics by design.

**Domain:** Healthcare (initial content focus). Architecture is domain-agnostic.
**Target:** Web-first (plain HTML/CSS/JS → React migration planned).
**Stage:** MVP — phases 0–2 complete, phase 3 in progress (proposals/voting/facilitator controls remaining).
**Dev environment:** GitHub Codespaces (primary). No local tooling assumed.

---

## Current Build Status (as of 2026-04-03)

**What's live and working:**
- All 9 pages deployed: `/` `/how-it-works` `/quiz` `/signin` `/threads` `/thread/{id}` `/new-thread` `/account` `/admin`
- Auth: Supabase magic link, JWT with client-side expiry detection
- Thread creation: registered tier can create threads (domain, title, central question, context)
- Signals: 4-type signal system (support/concern/need_info/block) on thread detail
- Posts: participant tier, phase-gated
- Facilitator request flow: account page → admin approval → tier promotion
- Admin page: approve/deny facilitator requests with audit log entries
- 15 policy domains seeded (healthcare + 14 others)
- Audit log: append-only, public API endpoint

**What is NOT yet built (Phase 3 remaining):**
- Proposal creation UI (PROPOSING phase)
- Voting UI (VOTING phase)
- Facilitator phase-advance controls (with required reason field)
- Public audit log page (filterable, unauthenticated)
- Full admin capabilities (create domains, funding pools, record allocations)

**What is explicitly deferred:**
- LLM integration (Phase 5 — do not add until Phase 4 deliberation is validated)
- React migration (no npm/build toolchain yet)
- Rate limiting, participant verification web flow, render.yaml

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
    schemas/      Pydantic schemas (API input/output)
    api/v1/       Route handlers
    core/         security.py (JWT), audit.py (log writer)
    db/session.py Async session factory
    static/       CSS, JS files served to browser
    templates/    HTML pages served by FastAPI
  alembic/        DB migrations
  tests/          pytest

docs/             Architecture, roadmap, LLM integration guide, decision log
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
   Use `core/audit.log_event()` only. The audit log is a capture detector,
   not just an accountability surface.

2. **Thread phase transitions are strict.** Use `thread.can_advance_to()`.
   Never update `Thread.status` directly — always go through the API route
   which validates the state machine and writes to audit log.

3. **Votes are immutable.** Once cast, a vote cannot be changed.
   The DB has a unique constraint on (proposal_id, voter_id).

4. **No reactions on posts.** No upvotes, downvotes, or likes.
   Signals are per-thread, not per-post.

5. **Phase gates are enforced server-side.** Never trust the client to
   enforce which actions are allowed in which phase.

6. **LLM is not yet integrated.** Do not add LLM calls until Phase 4
   of the roadmap. See `docs/llm-integration.md`.

7. **api.js must stay framework-agnostic.** No DOM manipulation in api.js —
   only fetch() calls that return data. This file must survive unchanged
   when the frontend migrates to React.

---

## Conventions

- **Python:** Prefer `async def` for all DB-touching code.
- **Models:** Use SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style.
- **Schemas:** Pydantic v2 `model_config = ConfigDict(from_attributes=True)`.
- **Routes:** Type-annotate all parameters. Use `Annotated[X, Depends(Y)]`.
- **Audit:** Call `core.audit.log_event()` inside the same transaction as the action.
- **HTML/JS:** Write one JavaScript function per UI component. Keep DOM
  manipulation out of api.js.

---

## What NOT to Do

- Do NOT add crypto, tokens, or blockchain. Explicitly excluded from MVP.
- Do NOT allow the LLM to post in threads. It is read-only.
- Do NOT skip the phase gate in any route, even "just for testing."
- Do NOT add upvotes, downvotes, or engagement metrics on posts.
- Do NOT store PII in the audit log payload.
- Do NOT commit `.env` files.
- Do NOT use `git push --force` on `main`.
- Do NOT add React, npm, or any build toolchain to the frontend yet.
  Plain HTML/CSS/JS only until the migration is explicitly planned.
- Do NOT reference or restore anything from the archived mobile/ scaffold.

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
- Audit log population (every action leaves a record)
- Vote immutability (can't vote twice)
- State machine correctness (can't skip phases)
- Audit log reconstructability (can you rebuild a decision from the log alone?)

See `backend/tests/test_threads.py` for examples.
