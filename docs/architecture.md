# System Architecture

## Thesis

Public deliberation can be translated into legitimate, transparent collective allocation
without outrage dynamics. This platform enforces that translation structurally, not
through content moderation alone.

---

## Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | FastAPI (Python 3.12) | Async, type-safe, auto-generates OpenAPI docs |
| **Database** | PostgreSQL 16 (Supabase) | Relational integrity for deliberation state machine |
| **ORM** | SQLAlchemy 2.0 (async) | Typed queries, Alembic migrations |
| **Auth** | Supabase Auth | Magic links = email friction without passwords |
| **Backend hosting** | Render (free tier → paid) | Git-deploy, no ops burden |
| **Frontend** | Plain HTML/CSS/JS (Phase 1–2), React (Phase 3+) | Web-first; no App Store overhead |
| **Frontend hosting** | Render (served from FastAPI, Phase 1–2), Vercel (Phase 3+) | Unified service until React migration |
| **Observability** | Sentry + structlog (JSON) | Error tracking; structured logs searchable in prod |

---

## Hosting Topology (Web MVP)

```
Browser (any device)
    │
    │ HTTPS
    ▼
Render.com (FastAPI — one service)
    ├── GET /api/v1/*    → FastAPI route handlers (JSON)
    ├── GET /static/*    → StaticFiles mount (CSS, JS)
    └── GET /*, /thread/* → FileResponse (HTML shells)
    │
    ├── PostgreSQL (Supabase)  ← managed
    └── Supabase Auth          ← magic link email auth
```

Dev environment: GitHub Codespaces (browser-based VS Code + Linux terminal).
Server started with `uvicorn app.main:app --reload` inside Codespaces — no local
tooling required.

---

## Frontend Architecture

### Phase 1: Plain HTML/CSS/JS (current)

Static files served directly from FastAPI. No build tools, no npm, no framework.

```
backend/app/
├── static/
│   ├── css/main.css          # all styles
│   └── js/
│       ├── api.js            # all fetch() calls — framework-agnostic
│       ├── auth.js           # JWT storage, login state
│       └── utils.js          # formatting, DOM helpers
└── templates/
    ├── index.html            # thread list (Page 1)
    ├── thread.html           # thread detail (Page 2)
    ├── signin.html           # magic link auth (Page 3)
    ├── audit.html            # public audit log (Page 9)
    └── admin.html            # admin surface (Page 10)
```

**Design principle:** `api.js` contains only fetch() calls with no DOM manipulation.
This file survives unchanged when migrating to React.

### Page Implementation Sequence

| Page | URL | Auth required | Status |
|---|---|---|---|
| 0 | Infrastructure (static mount, JS/CSS files) | — | Pending |
| 1 | Thread list | None | Pending |
| 2 | Thread detail (read-only) | None | Pending |
| 3 | Auth — magic link sign-in | None | Pending |
| 4 | Signal casting | Registered | Pending |
| 5 | Post creation | Participant | Pending |
| 6 | Proposal creation | Participant | Pending |
| 7 | Voting | Participant | Pending |
| 8 | Facilitator controls | Facilitator | Pending |
| 9 | Audit log | None | Pending |
| 10 | Admin | Admin | Pending |

### Phase 2: React (deferred)

When the HTML/JS frontend is validated with real users:
- Vite added as build tool
- `api.js` copied to React project unchanged
- Pages rebuilt as React components one at a time
- FastAPI serves React build output instead of `templates/`
- Frontend moves to Vercel (separate service)

---

## Identity Tiers

| Tier | How acquired | Capabilities |
|---|---|---|
| `registered` | Email magic link | Read threads, cast signals |
| `participant` | Identity verification (manual in MVP) | Post, vote, create proposals |
| `facilitator` | Appointed by admin | Advance thread phases, moderate posts |
| `admin` | Hardcoded / seeded | Create domains/pools, record allocations |

**Sybil resistance (non-crypto MVP):** Magic link auth creates email friction.
Identity verification for `participant` tier is manual in MVP (facilitator reviews
and grants via admin API). No phone verification or payment in MVP.

---

## Thread State Machine

```
OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED
```

- Transitions are one-directional. No going back.
- Only `facilitator` tier can advance phases.
- Every transition writes a required reason to the audit log.
- Phase gates enforce which actions are available:
  - `OPEN / DELIBERATING` → posts allowed
  - `PROPOSING` → proposals submitted
  - `VOTING` → votes cast
  - `CLOSED+` → read-only

---

## Anti-Outrage Design Choices

| Traditional forum | This platform |
|---|---|
| Upvotes/downvotes | Structured signals (support/concern/need_info/block) |
| Algorithmic feed | Chronological posts only |
| Reaction counts on posts | Signal counts on the thread (not posts) |
| Open-ended voting | Phase-gated; voting requires prior deliberation |
| Anonymous allocation | Every allocation decision is in the public audit log |

---

## Audit Log

The `audit_logs` table is **append-only** in application code. All significant
actions produce an entry:

- Thread phase changes (with facilitator's reason)
- Posts created/removed (with removal reason)
- Signals cast/changed
- Proposals created/status changed
- Votes cast
- Allocations decided (including vote summary snapshot)

The `/api/v1/audit` endpoint is public and unauthenticated. Any observer
can independently verify that platform decisions match the audit trail.

The audit log functions as a **capture detector** — a public, immutable record
that makes facilitator or institutional capture visible rather than hidden. This
is a primary legitimacy mechanism, not merely an accountability surface.

Future hardening: PostgreSQL trigger to enforce append-only at DB level.

---

## Data Model Overview

```
Domain
  └── Thread (status: OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED)
        ├── Post (author, body, parent_id; no reactions)
        ├── Signal (one per user per thread: support/concern/need_info/block)
        └── Proposal
              ├── Vote (one per participant per proposal: yes/no/abstain)
              └── AllocationDecision (pool_id, amount, vote_summary snapshot)

FundingPool (domain, total_amount, allocated_amount, currency=USD_SIM)
AuditLog (event_type, actor_id, target_type, target_id, payload — APPEND ONLY)
```

---

## Security Considerations

1. **JWT verification**: Supabase JWTs verified locally using HS256 + project secret.
   No network round-trip per request.
2. **Tier enforcement**: Every route declares its required tier via FastAPI
   dependency injection. No role claims are trusted from the JWT.
3. **Soft deletes**: Posts are soft-deleted; removal reason is recorded.
4. **No user PII in audit log**: `actor_id` is a UUID; display_name requires a
   separate lookup. This limits audit log exposure of identity.
5. **Rate limiting**: Not implemented in MVP. Add via Render's edge or `slowapi`.
6. **Moderator accountability**: All moderation actions (post removal, phase advance)
   are in the public audit log. Facilitators are not anonymous.

---

## Archived

**React Native mobile app** (`mobile/` — not in repo): The original iOS-targeted
frontend. Archived when pivoting to web-first (March 2025). Contains useful API
client patterns and component hierarchy reference. May inform a future native app
if the platform is validated with real users.
