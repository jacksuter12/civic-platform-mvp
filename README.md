# Civic Power Consortium — Deliberation Platform

**Thesis:** Public deliberation can be translated into legitimate, transparent
collective allocation without outrage dynamics.

This is a code-first MVP scaffold for an iOS app + REST backend. Healthcare is
the initial content focus. The architecture is domain-agnostic.

---

## What It Does

1. **Deliberation.** Participants discuss a structured prompt in a phase-gated thread.
2. **Signals.** Instead of likes/dislikes, participants cast structured signals
   (Support / Concern / Need Info / Block).
3. **Proposals.** When ready, participants submit formal proposals.
4. **Voting.** Participants vote yes/no/abstain on proposals (not on posts).
5. **Allocation.** Passed proposals receive resources from a simulated funding pool.
6. **Transparency.** Every action is in a public, append-only audit log.

---

## Repository Structure

```
backend/          Python + FastAPI REST API
mobile/           React Native + Expo iOS app
docs/             Architecture, roadmap, LLM integration plan
.github/          CI (GitHub Actions)
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

### Mobile

```bash
cd mobile
npm install
# Create mobile/.env with EXPO_PUBLIC_SUPABASE_URL, EXPO_PUBLIC_SUPABASE_ANON_KEY,
# EXPO_PUBLIC_API_BASE=http://localhost:8000/api/v1
npx expo start
# Scan QR code with Expo Go on iPhone, or press 'i' for iOS Simulator
```

---

## Deliberative Design Choices

| Choice | Why |
|---|---|
| No post upvotes/downvotes | Prevents outrage amplification and bandwagon effects |
| Chronological post order | No algorithmic amplification |
| Signals on threads, not posts | Surfaces distribution of sentiment, not popularity |
| Phase-gated threads | Forces deliberation before voting |
| Immutable votes | Prevents strategic vote-switching |
| Append-only audit log | Public accountability surface |
| Simulated funding pools | Demonstrates allocation without real money in MVP |
| Magic link auth | Identity friction without passwords or crypto |

---

## Development Phases

| Phase | Focus | Status |
|---|---|---|
| 0 | Local foundation: models, migrations, tests | Scaffold complete |
| 1 | Auth + mobile scaffold | Pending |
| 2 | Core deliberation flow | Pending |
| 3 | App Store (TestFlight) | Pending |
| 4 | First real deliberation | Pending |
| 5 | LLM read-only assistant | Pending |

See [docs/roadmap.md](docs/roadmap.md) for detail.

---

## Architecture

See [docs/architecture.md](docs/architecture.md).

## LLM Integration

See [docs/llm-integration.md](docs/llm-integration.md).

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, asyncpg
- **Database:** PostgreSQL (Supabase)
- **Auth:** Supabase Auth (magic links)
- **Mobile:** React Native, Expo 52, React Query, Zustand
- **CI/CD:** GitHub Actions
- **Hosting:** Render (backend), Supabase (DB/auth), EAS Build (mobile)

---

## License

MIT — see LICENSE.

*Civic Power Consortium is a nonprofit initiative.*
