# Civic Power Consortium — Deliberation Platform

**Thesis:** Public deliberation can be translated into legitimate, transparent
collective allocation without outrage dynamics. The architecture enforces that
translation structurally — not through content moderation alone.

---

## What It Does

1. **Deliberation.** Verified participants discuss a structured prompt in a
   phase-gated thread that moves through fixed stages.
2. **Signals.** Instead of likes/dislikes, participants cast structured signals
   (Support / Concern / Need Info / Block) on the thread — not on posts.
3. **Proposals.** In the proposing phase, participants submit formal proposals.
4. **Voting.** Participants vote yes/no/abstain on proposals (not on posts).
5. **Allocation.** Passed proposals receive resources from a simulated funding pool.
6. **Transparency.** Every action is recorded in a public, append-only audit log
   that any observer can use to independently verify platform decisions.

The output is not a petition. It is a documented collective decision, backed by
a hired lobbyist, delivered to the legislature.

---

## Repository Structure
```
backend/          Python + FastAPI REST API
docs/             Architecture, roadmap, LLM integration plan, decision log
index.html        Public landing page (served via GitHub Pages)
CLAUDE.md         Instructions for Claude Code
```

---

## Quick Start

### Backend
```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload
# → http://localhost:8000/docs (DEBUG=true)
```

Primary development environment: **GitHub Codespaces** (browser-based, no local
tooling required).

---

## Deliberative Design Choices

| Choice | Why |
|---|---|
| No post upvotes/downvotes | Prevents outrage amplification and bandwagon effects |
| Chronological post order | No algorithmic amplification |
| Signals on threads, not posts | Surfaces distribution of sentiment, not popularity |
| Phase-gated threads | Forces deliberation before voting |
| One-directional state machine | Prevents phase reopening to manipulate outcomes |
| Append-only audit log | Capture detector + public accountability surface |
| Facilitator accountability | All moderation actions are in the public audit log |
| Simulated funding pools | Demonstrates allocation without real money in MVP |
| Magic link auth | Identity friction without passwords or crypto |

---

## Development Phases

| Phase | Focus | Status |
|---|---|---|
| 0 | Backend scaffold: models, migrations, API routes | Complete |
| 1 | Web frontend: plain HTML/CSS/JS served from FastAPI | In progress |
| 2 | Core deliberation flow: post → signal → propose → vote | Pending |
| 3 | First real deliberation with real users | Pending |
| 4 | LLM read-only research assistant | Pending |

See [docs/roadmap.md](docs/roadmap.md) for detail.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.
See [docs/decisions.md](docs/decisions.md) for the institutional decision log.

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, asyncpg
- **Database:** PostgreSQL 16 (Supabase)
- **Auth:** Supabase Auth (magic links + JWT)
- **Frontend:** Plain HTML/CSS/JS (React migration planned for later phases)
- **Dev environment:** GitHub Codespaces
- **Hosting:** Render.com (backend + static frontend), Supabase (DB/auth)

---

## MVP Scope

- **Domain:** One healthcare sub-issue (prescription drug pricing)
- **Geography:** One U.S. state (Colorado)
- **Cohort:** Invite-only, 500–2,000 verified residents
- **Legal structure:** 501(c)(4) social welfare organization
- **Execution layer:** One experienced state lobbyist

---

## License

MIT — see LICENSE.

*Civic Power Consortium is a nonprofit initiative. Not yet launched.*
