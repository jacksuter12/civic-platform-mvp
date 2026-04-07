# Development Roadmap

## Philosophy

Build what can be scrutinized, not just what can be shipped.
Legitimacy is harder to test than functionality — plan for both.

---

## Phase 0 — Backend Foundation
**Status: Complete**

**Goal:** Runnable backend with correct data model.

**Tasks:**
- [x] FastAPI scaffold with SQLAlchemy 2.0 models, Alembic migrations, API routes
- [x] GitHub repository created, backend uploaded
- [x] Open Codespaces, install Claude Code
- [x] `pip install -e ".[dev]"` — all deps install in Codespaces
- [x] Copy `.env.example` → `.env`, fill in Supabase credentials
- [x] `alembic upgrade head` — migration runs against Supabase PG
- [x] `uvicorn app.main:app --reload` — server starts
- [x] `pytest` — all existing tests pass
- [x] Manually create `healthcare` domain via `/docs`
- [x] Seed script: 15 domains seeded (healthcare + 14 additional policy domains)
- [x] Create one thread, advance it through all phases manually
- [x] Verify audit log has entries for each action

**Definition of done:** Server running in Codespaces; full thread lifecycle
exercised via /docs; audit log populated.

---

## Phase 1 — Web Frontend: Read-Only Surface
**Status: Complete**

**Goal:** Public-facing web pages showing live data from the API. No auth yet.

**Tasks:**
- [x] Static file infrastructure (main.py updated, static/ and templates/ created)
- [x] Landing page (/) — public, no auth
- [x] How it works page (/how-it-works) — public, no auth
- [x] Quiz page (/quiz) — public, no auth
- [x] Thread list (/threads) — fetches and displays all threads with phase badges and signal counts
- [x] Thread detail (/thread/{id}) — displays thread, posts (chronological), signal bar
- [x] Deployed to Render.com alongside backend (single service)

**Definition of done:** A stranger can visit the URL, browse threads, and read
posts — without an account and without any auth.

---

## Phase 2 — Auth + Core Interactions
**Status: Complete**

**Goal:** End-to-end auth flow and the core interactive features.

**Tasks:**
- [x] Sign-in page (/signin) — magic link via Supabase, JWT stored in localStorage
- [x] Account page (/account) — display name, tier, facilitator request section
- [x] Header updates: show signed-in state, display_name, sign-out across all pages
- [x] Signal casting — four signal buttons on thread detail, registered tier only
- [x] Post creation — form on thread detail, participant tier only, phase-gated
- [x] Signal counts update immediately after casting (no page reload)
- [x] JWT expiry detection: client-side token expiry check clears stale tokens automatically
- [x] Bug fix: account page no longer crashes on expired JWT

**Definition of done:** A verified participant can sign in, view threads, cast
a signal, and write a post. A registered-only user can sign in and cast a signal
but not post.

---

## Phase 3 — Proposals, Voting, Facilitator Controls
**Status: In Progress**

**Goal:** Complete deliberation flow end-to-end.

**Completed:**
- [x] Thread creation page (/new-thread) — registered tier, domain select, title, central question, context
- [x] Facilitator request flow — account page application form → admin approval page
- [x] Admin page (/admin) — approve/deny facilitator requests, tier promotion, audit log entries
- [x] 15 policy domains seeded (healthcare + 14 more: education, defense, fiscal policy, etc.)
- [x] FacilitatorRequest model, migration, API routes (submit, list, approve, deny)
- [x] Facilitator phase-advance controls — phase advance UI on thread detail, required reason field (10–500 chars), audit log entry THREAD_PHASE_ADVANCED, facilitator-only
- [x] Proposal creation — form on thread detail, PROPOSING phase only, participant tier only, audit log entry PROPOSAL_CREATED
- [x] Voting — yes/no/abstain buttons on thread detail, VOTING phase only, participant tier only, one-vote enforcement via DB unique constraint, VOTE_CAST audit log entry, vote tallies visible to all
- [x] Public audit log API — GET /api/v1/audit, filterable by event_type/target_type/target_id/actor_id, paginated, no auth required

**Remaining:**
- [ ] Public audit log page (/audit) — HTML UI for the existing API, filterable, read-only, unauthenticated
- [ ] Full admin capabilities — create domains, funding pools, record allocations
- [ ] End-to-end test: full thread lifecycle with 3 test users

**Testing legitimacy (not just functionality):**
- Can a participant cheat the phase gate? (Try to vote while in DELIBERATING)
- Does the audit log correctly capture every facilitator action?
- Is the vote_summary in the allocation record accurate?
- Can you reconstruct a decision from the audit log alone?

**Definition of done:** Full thread lifecycle exercised by real users; audit log
reconstructs every decision.

---

## Phase 4 — First Real Deliberation
**Status: Not Started (blocked on Phase 3 completion)**

**Goal:** First real deliberation with healthcare domain participants.

**Tasks:**
- [ ] Recruit facilitators (2–3 trusted people) — use new facilitator request flow
- [ ] Design first deliberation prompt (healthcare focus — prescription drug pricing)
- [ ] Identity verification workflow for PARTICIPANT tier
  (MVP: facilitator manually promotes via API; no web flow yet)
- [ ] Notification system (email for phase changes — no push notifications in MVP)
- [ ] Participant onboarding: explain signals, phase gates, audit log
- [ ] Run deliberation, observe: does it feel legitimate?
- [ ] Post-deliberation debrief: what would participants change?
- [ ] Backend: move to paid Render tier (always-on, not sleeping)

---

## Phase 5 — LLM Assistant

See `docs/llm-integration.md` for full design.

**Gate:** Only begin after Phase 4 is validated. Don't add LLM until
deliberation without it is working.

---

## Development Environment

| Work | Where |
|---|---|
| All backend dev | GitHub Codespaces (primary) |
| Database | Supabase cloud (free tier) |
| Auth | Supabase cloud |
| CI/CD | GitHub Actions |
| Production | Render.com |
| Landing page | GitHub Pages (jacksuter12.github.io/civic-platform-mvp) |

**Codespaces notes:**
- Start each session: `uvicorn app.main:app --reload` (auto-suspends after 30 min idle)
- Claude Code installed once per Codespace: `curl -fsSL https://claude.ai/install.sh | bash`
- `.env` file configured inside Codespace — never committed to git
- Free tier: 120 core-hours/month (sufficient for solo development)

---

## Testing Legitimacy

Functional tests check correctness. Legitimacy tests check trustworthiness.

**Legitimacy test questions:**
1. Can you reconstruct every allocation decision from the audit log alone?
2. Can a facilitator act without it being recorded? (Answer must be: no)
3. Can a participant vote twice? (Answer must be: no — DB unique constraint)
4. Can a thread skip the deliberation phase? (Answer must be: no — state machine)
5. Do block signals get surfaced even if they're a minority? (Answer must be: yes)
6. Is the vote_summary in the allocation record a snapshot, not a live query?
   (Answer must be: yes — immutable at decision time)
7. Can you tell from the audit log alone whether a facilitator advanced a phase
   without a stated reason? (Answer must be: no — reason is required)
