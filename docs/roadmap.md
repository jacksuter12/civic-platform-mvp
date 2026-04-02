# Development Roadmap

## Philosophy

Build what can be scrutinized, not just what can be shipped.
Legitimacy is harder to test than functionality — plan for both.

---

## Phase 0 — Backend Foundation
**Status: Complete (scaffold built; Codespaces environment pending verification)**

**Goal:** Runnable backend with correct data model.

**Tasks:**
- [x] FastAPI scaffold with SQLAlchemy 2.0 models, Alembic migrations, API routes
- [x] GitHub repository created, backend uploaded
- [ ] Open Codespaces, install Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`
- [ ] `pip install -e ".[dev]"` — verify all deps install in Codespaces
- [ ] Copy `.env.example` → `.env`, fill in Supabase credentials
- [ ] `alembic upgrade head` — verify migration runs against Supabase PG
- [ ] `uvicorn app.main:app --reload` — verify server starts
- [ ] `pytest` — all existing tests pass
- [ ] Manually create `healthcare` domain via `/docs` (DEBUG=true)
- [ ] Create one thread, advance it through all phases manually
- [ ] Verify audit log has entries for each action

**Definition of done:** Server running in Codespaces; full thread lifecycle
exercised via /docs; audit log populated.

---

## Phase 1 — Web Frontend: Read-Only Surface

**Goal:** Public-facing web pages showing live data from the API. No auth yet.

**Tasks:**
- [ ] Page 0: Static file infrastructure (update main.py, create static/ and templates/)
- [ ] Page 1: Thread list — fetches and displays all threads with phase badges and signal counts
- [ ] Page 2: Thread detail — displays thread, posts (chronological), signal bar (read-only)
- [ ] Deployed to Render.com alongside backend (single service)

**Definition of done:** A stranger can visit the URL, browse threads, and read
posts — without an account and without any auth.

**What is NOT done in Phase 1:**
- No sign-in
- No signal casting
- No posting

---

## Phase 2 — Auth + Core Interactions

**Goal:** End-to-end auth flow and the core interactive features.

**Tasks:**
- [ ] Page 3: Auth — magic link sign-in via Supabase, JWT stored in localStorage
- [ ] Header updates: show signed-in state, display_name, sign-out across all pages
- [ ] Page 4: Signal casting — four signal buttons on thread detail, registered tier only
- [ ] Page 5: Post creation — form on thread detail, participant tier only, phase-gated
- [ ] Signal counts update immediately after casting (no page reload)

**Definition of done:** A verified participant can sign in, view threads, cast
a signal, and write a post. A registered-only user can sign in and cast a signal
but not post.

---

## Phase 3 — Proposals, Voting, Facilitator Controls

**Goal:** Complete deliberation flow end-to-end.

**Tasks:**
- [ ] Page 6: Proposal creation — form visible in PROPOSING phase, participant tier
- [ ] Page 7: Voting — yes/no/abstain buttons in VOTING phase, one vote per proposal
- [ ] Page 8: Facilitator controls — phase advance UI with required reason field
- [ ] Page 9: Public audit log — filterable, read-only, unauthenticated
- [ ] Page 10: Admin — create domains, funding pools, record allocations
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

**Goal:** First real deliberation with healthcare domain participants.

**Tasks:**
- [ ] Recruit facilitators (2–3 trusted people)
- [ ] Design first deliberation prompt (healthcare focus — prescription drug pricing)
- [ ] Identity verification workflow for PARTICIPANT tier
  (MVP: facilitator manually reviews and grants via admin API)
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
