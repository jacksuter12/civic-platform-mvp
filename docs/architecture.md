# System Architecture

_Last updated: 2026-04-03. Reflects current deployed state._

---

## Thesis

Public deliberation can be translated into legitimate, transparent collective allocation without outrage dynamics. This platform enforces that translation structurally, not through content moderation alone.

---

## Stack

| Layer | Technology | Notes |
|---|---|---|
| **Backend** | FastAPI (Python 3.12) | Async, type-safe, auto-generates OpenAPI docs in dev |
| **Database** | PostgreSQL 16 (Supabase cloud) | Relational integrity for deliberation state machine |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | Typed queries; migrations in `backend/alembic/` |
| **Auth** | Supabase Auth (magic links + JWT) | Email friction without passwords; JWTs verified locally |
| **Frontend** | Plain HTML/CSS/JS | Served directly from FastAPI. No npm, no build step. React migration deferred until user validation. |
| **Hosting** | Render.com (single web service) | Git-deploy from `main`; config currently in Render dashboard only (no `render.yaml` yet) |
| **Observability** | Sentry + structlog (JSON) | Error tracking; structured logs searchable in prod |
| **Dev environment** | GitHub Codespaces | Browser-based VS Code + Linux terminal; no local tooling required |

---

## Hosting Topology

```
Browser (any device)
    │
    │ HTTPS
    ▼
Render.com — FastAPI web service
    ├── GET /api/v1/*        → route handlers (JSON responses)
    ├── GET /static/*        → StaticFiles mount (CSS, JS assets)
    └── GET /[page routes]   → FileResponse (HTML shells)
         │
         ├── Supabase PostgreSQL   ← all application data
         └── Supabase Auth         ← magic link email, JWT issuance
```

Dev: `uvicorn app.main:app --reload` inside Codespaces on port 8000.

---

## Frontend Structure

No build tooling. All files are plain HTML/CSS/JS.

```
backend/app/
├── static/
│   ├── css/
│   │   └── main.css          # all shared styles
│   └── js/
│       ├── api.js            # all fetch() calls — no DOM, framework-agnostic
│       ├── auth.js           # JWT storage, expiry check, login state
│       ├── nav.js            # shared navigation bar
│       └── utils.js          # formatting helpers (timeAgo, capitalize, etc.)
└── templates/
    ├── index.html            # public landing page — platform thesis, stats, donation model
    ├── how-it-works.html     # deep mechanics — phase flow, signals, audit log, failure modes
    ├── quiz.html             # issue-position quiz (static for now)
    ├── signin.html           # magic link sign-in / account creation
    ├── threads.html          # thread list with signal counts and phase badges
    ├── thread.html           # thread detail — posts, signals, proposals, voting, facilitator controls
    ├── new-thread.html       # create a new discussion thread (registered+ required)
    ├── account.html          # profile, display name, facilitator status / application
    └── admin.html            # facilitator request approval queue (admin only)
```

**Design constraint:** `api.js` contains only `fetch()` calls and data parsing — no DOM
manipulation. This file is intentionally framework-agnostic so it survives unchanged
when the frontend migrates to React.

---

## Pages — Current Status

| URL | Template | Auth required | What it does |
|---|---|---|---|
| `/` | `index.html` | None | Landing page: platform thesis, lobbying stats, donation model explainer |
| `/how-it-works` | `how-it-works.html` | None | Full mechanics: phase flow, signals, audit log demo, failure modes |
| `/quiz` | `quiz.html` | None | Issue-position quiz (currently static) |
| `/signin` | `signin.html` | None | Magic link auth; creates account on first sign-in |
| `/threads` | `threads.html` | None (read); Registered (create button) | Thread list with signal bars and phase badges |
| `/thread/{id}` | `thread.html` | None (read); Registered (signals); Registered (post/vote/propose) | Full thread: discussion, signals, proposals, voting, facilitator panel |
| `/new-thread` | `new-thread.html` | Registered | Create a new discussion thread |
| `/account` | `account.html` | Registered | Profile, display name changes, facilitator application |
| `/admin` | `admin.html` | Admin | Pending facilitator request queue with approve/deny |

---

## What's Working

- **Full thread lifecycle** — all 6 phases (OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED)
- **Auth** — Supabase magic link sign-in; JWT verified on every API call
- **Signal casting** — one signal per user per thread; block signals always surfaced
- **Post creation** — with threading (replies); chronological, no reactions
- **Proposal creation** — in PROPOSING phase only
- **Voting** — immutable votes in VOTING phase; results hidden until CLOSED
- **Facilitator controls** — phase advance with required reason, written to audit log
- **Facilitator request flow** — users apply on account page; admin approves/denies at `/admin`; tier promotion is audit-logged
- **Audit log** — public, append-only, queryable via `GET /api/v1/audit`
- **15 policy domains** — seeded: Healthcare, Education, Defense, Fiscal Policy, Monetary Policy, Social Security, Housing, Immigration, Criminal Justice, Environment & Energy, Infrastructure, Labor, Trade, Civil Rights, Drug Policy
- **Landing pages** — `/`, `/how-it-works` with cited stats, donation model, failure modes

---

## What's Not Yet Built

| Item | Notes |
|---|---|
| **LLM assistant** | Phase 5 of roadmap. Read-only summarization. See `docs/llm-integration.md`. |
| **Full admin dashboard** | Current `/admin` handles only facilitator requests. Domain management, pool creation, allocation recording still done via API or direct DB. |
| **`render.yaml`** | Render deployment config exists only in the Render dashboard. Should be committed to repo for reproducibility. |
| **Rate limiting** | No per-IP or per-user rate limiting. Add via `slowapi` or Render edge when needed. |
| **Participant identity verification** | Currently manual — admin promotes via facilitator request flow. No automated verification. |
| **React migration** | Deferred until web MVP is validated with real users. `api.js` is designed to survive the migration unchanged. |
| **Render.yaml** | Deployment config in Render dashboard only, not in repo. |

---

## Identity Tiers

| Tier | How acquired | Capabilities |
|---|---|---|
| `registered` | Email magic link (auto on first sign-in) | Read threads, cast signals, create posts, create threads, submit proposals, vote, apply for facilitator |
| `participant` | _Reserved for future identity verification_ | Currently same as registered; will require additional verification step when implemented |
| `facilitator` | Approved via facilitator request flow at `/admin` | Advance thread phases, remove posts (with reason, audit-logged) |
| `admin` | Seeded or manually set in DB | All of the above plus facilitator request approval |

**Note on tier gating:** Thread creation was intentionally lowered to `registered` for
the MVP launch cohort. The `participant` tier will be re-activated as a gate when
identity verification is implemented.

**Sybil resistance (MVP):** Magic link auth creates email friction. No phone
verification or payment in MVP. Facilitator tier requires manual approval via the
admin queue.

---

## Thread State Machine

```
OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED
```

- Transitions are **one-directional**. No going back.
- Only `facilitator` tier can advance phases.
- Every transition writes a **required reason** to the audit log.
- Phase gates enforce which actions are available — enforced at the database level, not just the UI:
  - `OPEN / DELIBERATING` → posts and signals allowed
  - `PROPOSING` → proposals submitted; posting locked
  - `VOTING` → votes cast; immutable once submitted; results hidden until CLOSED
  - `CLOSED / ARCHIVED` → read-only

---

## Anti-Outrage Design Choices

| Traditional forum | This platform |
|---|---|
| Upvotes / downvotes on posts | Structured signals on the thread (support / concern / need_info / block) |
| Algorithmic feed | Chronological posts only — no ranking |
| Reaction counts per post | Signal distribution per thread |
| Open-ended voting | Phase-gated: voting requires prior deliberation |
| Anonymous allocation | Every allocation decision is in the public audit log |
| Unlimited voting window | Votes immutable once cast; no strategic switching |
| Minority dissent buried | Block signals always surfaced prominently to facilitator |

---

## Annotation System (v1: Wiki Only)

Annotations allow permissioned reviewers (`annotator` capability) to give in-place
feedback on content — attaching a comment, reaction, or reply to a specific passage.

**Target model:** The `annotations` table is target-agnostic. Every annotation carries
a `target_type` field (`wiki` | `post` | `proposal` | `document`) and a `target_id`.
The same backend routes and frontend module serve annotations on any content type.
v1 ships on wiki articles only. Extension to posts and proposals is supported by the
data model but requires a separate decision before implementation.

**Anchoring:** Annotations are anchored to a text range using Hypothesis's open-source
libraries (`dom-anchor-text-quote` and related). When text anchoring fails (the anchor
passage has been edited out of the document), the system falls back to section-level
attachment so the annotation is not silently lost.

**Reactions:** Annotations support `endorse` and `needs_work` reactions. These are
editorial signals only — they are never used to sort, filter, or rank content. See the
"Reactions Permitted on Individual Contributions" decision (2026-04-09).

**Audit:** All annotation actions (create, react, reply, soft-delete) write to the
audit log. Soft deletes only — no hard deletion of annotation records.

---

## Audit Log

The `audit_logs` table is **append-only** in application code (`core/audit.log_event()`
is the only write path — no UPDATE or DELETE). All significant actions produce an entry:

- Thread created / phase advanced (with facilitator's stated reason)
- Posts created / removed (with removal reason)
- Signals cast / updated
- Proposals created / status changed
- Votes cast
- Allocations decided (vote summary snapshot in payload)
- User tier changes (with reason)
- Facilitator requests submitted / approved / denied

The `/api/v1/audit` endpoint is public and unauthenticated. Any observer can
independently verify that platform decisions match the audit trail.

The audit log functions as a **capture detector** — a public, immutable record that
makes facilitator or institutional capture visible rather than hidden. This is a
primary legitimacy mechanism, not merely an accountability surface.

_Future hardening: PostgreSQL trigger to enforce append-only at the DB level._

---

## Data Model Overview

```
Domain (slug, name, is_active)
  └── Thread (OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED)
        ├── Post (author, body, parent_id; no reactions; soft-deleted)
        ├── Signal (one per user per thread: support/concern/need_info/block)
        └── Proposal
              ├── Vote (one per participant per proposal: yes/no/abstain; immutable)
              └── AllocationDecision (pool_id, amount, vote_summary snapshot)

FundingPool (domain, total_amount, allocated_amount, currency=USD_SIM)
FacilitatorRequest (user_id, reason, status: pending/approved/denied, reviewed_by_id)
AuditLog (event_type, actor_id, target_type, target_id, payload — APPEND ONLY)
```

---

## Security

1. **JWT verification** — Supabase JWTs verified locally (HS256 or ES256 via JWKS).
   No network round-trip per request. Expired tokens are detected client-side by
   `auth.js` before any API call is made.
2. **Tier enforcement** — Every route declares its required tier via FastAPI dependency
   injection (`RegisteredUser`, `FacilitatorUser`, `AdminUser`). No role claims are
   trusted from the JWT itself.
3. **Phase gates server-side** — Action availability (post, propose, vote) is enforced
   at the API layer, not just the UI. The client cannot bypass phase gates.
4. **Soft deletes** — Posts are soft-deleted; body replaced with tombstone, removal
   reason recorded in audit log.
5. **No PII in audit log** — `actor_id` is a UUID; display_name requires a separate
   lookup. Limits exposure of identity in the public log.
6. **Moderator accountability** — All facilitator actions (phase advance, post removal)
   are in the public audit log with a required stated reason.
7. **Vote immutability** — DB unique constraint on `(proposal_id, voter_id)`. Cannot
   vote twice on the same proposal.
8. **Rate limiting** — Not implemented in MVP. Add via `slowapi` or Render edge.

---

## Archived

**React Native mobile app** — The original iOS-targeted frontend was archived when
pivoting to web-first (early 2025). Not in the repository. May inform a future native
app if the platform is validated with real users.
