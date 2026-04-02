# CLAUDE.md — Civics Platform

This file is read by Claude Code at the start of every session.

## Project Overview

Civic Power Consortium — a nonprofit civic platform converting deliberation
into legitimate collective allocation. No outrage dynamics by design.

**Domain:** Healthcare (initial content focus). Architecture is domain-agnostic.
**Target:** Apple App Store (iOS) + web browser (future).
**Stage:** MVP scaffold.

---

## Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 (async) + Alembic |
| Database | PostgreSQL (Supabase cloud) |
| Auth | Supabase Auth (magic links) |
| Mobile | React Native + Expo 52 |
| Hosting | Render (backend) + Supabase (DB/Auth) |
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
  alembic/        DB migrations
  tests/          pytest

mobile/           React Native + Expo app
  src/
    api/client.ts API client (typed fetch wrappers)
    store/        Zustand (auth state only)
    screens/      Screen components
    components/   Reusable UI components

docs/             Architecture, roadmap, LLM integration guide
```

---

## Dev Commands

```bash
# Backend
cd backend
pip install -e ".[dev]"
cp .env.example .env          # fill in Supabase credentials
alembic upgrade head           # run migrations
uvicorn app.main:app --reload  # dev server at :8000
pytest                         # run tests
ruff check .                   # lint
mypy app --ignore-missing-imports  # type check

# Mobile
cd mobile
npm install
npx expo start                 # starts dev server + QR code for Expo Go
```

---

## Key Architectural Constraints

1. **Audit log is append-only.** Never write UPDATE/DELETE on `audit_logs`.
   Use `core/audit.log_event()` only.

2. **Thread phase transitions are strict.** Use `thread.can_advance_to()`.
   Never update `Thread.status` directly — always go through the API route
   which validates the state machine and writes to audit log.

3. **Votes are immutable.** Once cast, a vote cannot be changed.
   The DB has a unique constraint on (proposal_id, voter_id).

4. **No reactions on posts.** No upvotes, downvotes, or likes.
   Signals are per-thread, not per-post.

5. **Phase gates are enforced server-side.** Never trust the client to
   enforce which actions are allowed in which phase.

6. **LLM is not yet integrated.** Do not add LLM calls until Phase 5
   of the roadmap. See `docs/llm-integration.md`.

---

## Conventions

- **Python:** Prefer `async def` for all DB-touching code.
- **Models:** Use SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style.
- **Schemas:** Pydantic v2 `model_config = ConfigDict(from_attributes=True)`.
- **Routes:** Type-annotate all parameters. Use `Annotated[X, Depends(Y)]`.
- **Audit:** Call `core.audit.log_event()` inside the same transaction as the action.
- **TypeScript:** Strict mode. No `any` without a comment explaining why.

---

## What NOT to Do

- Do NOT add crypto, tokens, or blockchain. This is explicitly excluded from MVP.
- Do NOT allow the LLM to post in threads. It is read-only.
- Do NOT skip the phase gate in any route, even "just for testing."
- Do NOT add upvotes, downvotes, or engagement metrics on posts.
- Do NOT store PII in the audit log payload.
- Do NOT commit `.env` files.
- Do NOT use `git push --force` on `main`.

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

See `backend/tests/test_threads.py` for examples.
