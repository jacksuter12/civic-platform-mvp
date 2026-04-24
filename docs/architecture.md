# System Architecture

_Last updated: 2026-04-23. Reflects current deployed state._

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
│   │   └── main.css              # all shared styles
│   └── js/
│       ├── api.js                # all fetch() calls — no DOM, framework-agnostic
│       ├── auth.js               # JWT storage, expiry check, login state
│       ├── nav.js                # shared navigation bar
│       ├── utils.js              # formatting helpers (timeAgo, capitalize, esc, etc.)
│       ├── config.js             # client-side configuration (API base URL, etc.)
│       ├── thread.js             # thread detail UI — posts, signals, proposals, voting
│       ├── annotations.js        # annotation CRUD operations
│       ├── annotation_ui.js      # annotation rendering, highlighting, reaction UI
│       └── annotation_anchor.js  # text selection and anchor tracking (Hypothesis-based)
└── templates/
    ├── index.html                # public landing page — thesis, stats, donation model
    ├── how-it-works.html         # deep mechanics — phase flow, signals, audit log
    ├── quiz.html                 # issue-position quiz (static for now)
    ├── signin.html               # magic link sign-in / account creation
    ├── account.html              # profile, communities, activity history, facilitator request
    ├── communities.html          # community directory
    ├── community_home.html       # community landing page (public if is_public)
    ├── community_members.html    # public member list (display name + tier, no PII)
    ├── community_admin.html      # community admin: facilitator requests, tier promotion
    ├── threads.html              # thread list scoped to community
    ├── thread.html               # thread detail — posts, signals, proposals, voting
    ├── new-thread.html           # create a new discussion thread (registered+ required)
    ├── admin.html                # platform admin: communities, annotators, user list
    ├── audit.html                # platform-level audit log viewer
    ├── wiki_index.html           # wiki table of contents
    └── wiki_article.html         # individual wiki article with inline annotations
```

**Design constraint:** `api.js` contains only `fetch()` calls and data parsing — no DOM
manipulation. This file is intentionally framework-agnostic so it survives unchanged
when the frontend migrates to React.

---

## Pages — Current Status

| URL | Template | Auth required | What it does |
|---|---|---|---|
| `/` | `index.html` | None | Landing page: platform thesis, lobbying stats, donation model |
| `/how-it-works` | `how-it-works.html` | None | Full mechanics: phase flow, signals, audit log, failure modes |
| `/quiz` | `quiz.html` | None | Issue-position quiz (currently static) |
| `/signin` | `signin.html` | None | Magic link auth; creates account on first sign-in |
| `/account` | `account.html` | Registered | Profile, communities, activity history feed, facilitator request |
| `/communities` | `communities.html` | None | Community directory |
| `/c/{slug}` | `community_home.html` | None (if public) | Community landing: threads, member count, description |
| `/c/{slug}/threads` | `threads.html` | None (read); Registered (create) | Thread list scoped to community |
| `/c/{slug}/thread/{id}` | `thread.html` | None (read); Registered (interact) | Full thread: posts, signals, proposals, voting, facilitator panel |
| `/c/{slug}/new-thread` | `new-thread.html` | Registered member | Create a new thread in this community |
| `/c/{slug}/audit` | `audit.html` | None (if public) | Community-scoped audit log |
| `/c/{slug}/members` | `community_members.html` | None (if public) | Member list (display name + tier, no PII) |
| `/c/{slug}/admin` | `community_admin.html` | Facilitator/Admin | Facilitator requests, tier promotion |
| `/admin` | `admin.html` | Platform admin | Community creation, annotator grants, user list |
| `/audit` | `audit.html` | None | Platform-level audit log (community_id IS NULL events only) |
| `/wiki` | `wiki_index.html` | None | Global wiki table of contents |
| `/wiki/{slug}` | `wiki_article.html` | None (read); Annotator (annotate) | Wiki article with inline annotations |
| `/threads` `/thread/{id}` `/new-thread` | — | — | 302 redirect → `/c/test/...` (legacy URLs) |

---

## What's Working

**Infrastructure**
- **Multi-community architecture** — `Community` and `CommunityMembership` tables; `platform_role` on users (`user` | `platform_admin`); all deliberative actions community-scoped
- **17 Alembic migrations** — head: `d6e7f8a9b0c1`; 58 passing tests
- **Auth** — Supabase magic link sign-in; JWT verified on every API call; client-side expiry detection

**Pages and routes**
- **Community directory** — `/communities` — public listing of communities
- **Community home** — `/c/{slug}` — landing page, active threads, member count
- **Community admin** — `/c/{slug}/admin` — facilitator request queue, member tier promotion
- **Community members** — `/c/{slug}/members` — public display name + tier list
- **Community audit** — `/c/{slug}/audit` — scoped to community events; public if community is public
- **Platform admin** — `/admin` — community creation, annotator capability management, user list
- **Platform audit** — `/audit` — platform-level events only (community_id IS NULL)
- **Wiki** — `/wiki`, `/wiki/{slug}` — 16 articles with TOC, prev/next navigation
- **Legacy redirects** — `/threads`, `/thread/{id}`, `/new-thread` → `/c/test/...`

**Deliberation**
- **Full thread lifecycle** — all 6 phases (OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED)
- **Signal casting** — one signal per user per thread; polymorphic targets (thread/post/proposal); block signals always surfaced
- **Post creation** — phase-gated (OPEN/DELIBERATING); chronological, no reactions, soft-deleted by facilitator
- **Proposals** — PROPOSING phase only; versioned (edit snapshots); proposal comments; amendments (submit / accept / reject)
- **Voting** — yes/no/abstain; immutable once cast; DB unique constraint; results hidden until CLOSED
- **Facilitator controls** — phase advance with required reason, written to audit log; community-scoped (a Redlands facilitator cannot act in another community's threads)
- **Facilitator request flow** — account page application → community admin approval → `CommunityMembership.tier` promoted, audit-logged

**Account and user**
- **Account page** — 10 sections: profile, communities, activity history, facilitator request, etc.
- **Activity history feed** — filterable by action type (posts/votes/signals/proposals/amendments), searchable, chronological
- **Sticky side nav** — account page sections with scroll-aware highlighting

**Wiki and annotations**
- **Inline annotation system** — `annotator` capability required; text-range anchoring (Hypothesis-based) with section-level fallback; all actions audit-logged
- **Annotation reactions** — `endorse` / `needs_work`; editorial only, never used for ranking or sorting
- **15 policy domains** — seeded: Healthcare, Education, Defense, Fiscal Policy, Monetary Policy, Social Security, Housing, Immigration, Criminal Justice, Environment & Energy, Infrastructure, Labor, Trade, Civil Rights, Drug Policy

---

## What's Not Yet Built

| Item | Notes |
|---|---|
| **LLM assistant** | Phase 5 of roadmap. Read-only summarization only. See `docs/llm-integration.md`. |
| **Real communities seeded** | `test` community exists. `redlands`, `civic-power-consortium`, `macro-circle` must be created via `/admin`. |
| **Allocation admin UI** | API routes exist for pools and allocations; no admin form in the UI yet. |
| **Participant tier enforcement** | All substantive actions gated at `registered` for now. `participant` tier is in the schema as a reserved future state for scoped identity verification. |
| **`render.yaml`** | Render deployment config exists only in the Render dashboard. Should be committed to repo for reproducibility. |
| **Rate limiting** | No per-IP or per-user rate limiting. Add via `slowapi` or Render edge when needed. |
| **React migration** | Deferred until web MVP is validated with real users. `api.js` is designed to survive the migration unchanged. |
| **End-to-end test** | Full thread lifecycle with 3 test users (real browser flow) not yet scripted. |

---

## Identity Tiers

Tiers are now stored on `CommunityMembership`, not on `users`. A user's tier is
per-community — being a facilitator in one community confers no privileges in another.
`users.tier` is vestigial and will be dropped in a future cleanup migration.

**Community-scoped tiers (CommunityMembership.tier):**

| Tier | How acquired | Capabilities |
|---|---|---|
| `registered` | Joining a community (auto on email magic link for the initial community) | Read threads, cast signals, create posts, create threads, submit proposals, vote, submit amendments, apply for facilitator |
| `participant` | _Reserved for future identity verification_ | Currently same as registered; will require scoped verification (e.g., voter file for Redlands) when implemented |
| `facilitator` | Approved via facilitator request flow; community admin promotes | Advance thread phases, remove posts (with reason, audit-logged). Scoped to the community where approved. |
| `admin` | Seeded or manually promoted in DB | All facilitator capabilities + approve/deny facilitator requests, promote member tiers |

**Platform-level distinction (users.platform_role):**

| Role | How acquired | Capabilities |
|---|---|---|
| `user` | Default | Normal participant in communities they belong to |
| `platform_admin` | Seeded or manually set | Create communities, grant/revoke annotator capability, list all users |

**FastAPI dependency injection:**
- `RegisteredUser` — requires any community membership at `registered` or above in the target community
- `FacilitatorUser` / `CommunityAdminUser` — requires `facilitator` or `admin` membership in the target community
- `PlatformAdminUser` — requires `user.platform_role == 'platform_admin'`
- Do not use the old `AdminUser` dep for new routes — it checks the vestigial `users.tier`

**Sybil resistance (MVP):** Magic link auth creates email friction. No phone
verification or payment in MVP. Facilitator tier requires community admin approval.
Cross-community isolation is the primary trust boundary at this stage: a registered
Redlands member cannot act in Macro Circle without a separate membership.

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
Community (slug, name, type, is_public, is_invite_only, description)
  ├── CommunityMembership (user_id, tier: registered/participant/facilitator/admin)
  ├── FundingPool (community-scoped, total_amount, allocated_amount, currency=USD_SIM)
  ├── FacilitatorRequest (user_id, reason, status: pending/approved/denied, reviewed_by)
  └── Domain (slug, name, is_active — community-scoped)
        └── Thread (OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED)
              ├── Post (author, body, parent_id; soft-deleted; no ranking)
              ├── Signal (one per user per target: support/concern/need_info/block;
              │          polymorphic: thread/post/proposal/comment/amendment)
              └── Proposal
                    ├── ProposalVersion (immutable edit snapshots)
                    ├── ProposalComment (during voting)
                    ├── Amendment (submit/accept/reject workflow)
                    ├── Vote (yes/no/abstain; immutable; one per user; DB unique constraint)
                    └── AllocationDecision (pool_id, amount, vote_summary snapshot)

User (email, display_name, platform_role: user|platform_admin, is_annotator)
AuditLog (event_type, actor_id, target_type, target_id, payload, community_id — APPEND ONLY)
  # community_id IS NULL for platform events; set for all community-scoped events

Annotation (target_type: wiki|post|proposal|document, target_id, anchor, body)
  └── AnnotationReaction (user_id, reaction_type: endorse|needs_work)
```

---

## Security

1. **JWT verification** — Supabase JWTs verified locally (HS256 or ES256 via JWKS).
   No network round-trip per request. Expired tokens are detected client-side by
   `auth.js` before any API call is made.
2. **Community-scoped tier enforcement** — Every route declares its required tier via
   FastAPI dependency injection (`RegisteredUser`, `FacilitatorUser`, `PlatformAdminUser`,
   `CommunityAdminUser`). No role claims are trusted from the JWT itself. `users.tier` is
   vestigial; do not use the old `AdminUser` dep for new routes.
3. **Cross-community isolation** — Facilitator and admin tiers are community-scoped. A
   facilitator in Community A cannot advance phases or approve requests in Community B.
4. **Phase gates server-side** — Action availability (post, propose, vote) is enforced
   at the API layer, not just the UI. The client cannot bypass phase gates.
5. **Soft deletes** — Posts are soft-deleted; body replaced with tombstone, removal
   reason recorded in audit log.
6. **No PII in audit log** — `actor_id` is a UUID; display_name requires a separate
   lookup. Limits exposure of identity in the public log.
7. **Moderator accountability** — All facilitator actions (phase advance, post removal)
   are in the public audit log with a required stated reason.
8. **Vote immutability** — DB unique constraint on `(proposal_id, voter_id)`. Cannot
   vote twice on the same proposal.
9. **Rate limiting** — Not implemented in MVP. Add via `slowapi` or Render edge.

---

## Archived

**React Native mobile app** — The original iOS-targeted frontend was archived when
pivoting to web-first (early 2025). Not in the repository. May inform a future native
app if the platform is validated with real users.
