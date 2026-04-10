# Civic Platform — Decision Log

## Purpose
This file records every significant design decision for the civic deliberation platform. It serves as institutional memory across all project workstreams (Constitution & Strategy, Platform Development, Mechanism Design).

## Format
Each entry follows this template. Copy it when adding new decisions.

```
## [YYYY-MM-DD] — [Short Decision Title]
**Status:** Active | Superseded by [link] | Under review
**Domain:** Strategy | Technical | Mechanism | Legal | Governance
**Context:** Why this decision came up.
**Options considered:** What alternatives were evaluated.
**Decision:** What was chosen.
**Reasoning:** Why this option over the others.
**Implications:** What this constrains or enables downstream.
**Revisit if:** Under what conditions we'd reconsider.
```

---

# Active Decisions

---

## 2026-02-28 — Problem Framing: Coordination Gap, Not Ideology
**Status:** Active
**Domain:** Strategy
**Context:** The project needed a precise, falsifiable problem statement to anchor all downstream design work.
**Options considered:** (a) Frame around a normative axiom ("outcomes over outrage"), (b) Frame around a structural diagnosis (the coordination gap).
**Decision:** Frame around the structural coordination gap. The canonical problem statement: "No persistent, self-initiating institutional mechanism exists for converting majority-but-moderate-intensity citizen preferences on broad, cross-cutting policy issues into concentrated political force capable of overcoming the organized opposition of concentrated economic interests — when those interests have systematically shaped both the legislative environment and the information environment in which citizen preferences are formed."
**Reasoning:** A normative axiom (like "outcomes over outrage") is a slogan that prematurely commits the project to a stance that may not survive contact with real design constraints. The coordination gap is an empirical observation that can be stress-tested and falsified. It also frees the design process to make pragmatic choices — some engagement, some identity expression, some emotional resonance — rather than being bound by an ideological commitment to pure rationality.
**Implications:** All design choices should be evaluated against "does this help convert diffuse preferences into concentrated political force?" rather than "does this optimize for outcomes over outrage?" Some features that serve identity expression or community belonging may be warranted if they sustain participation in the coordination function.
**Revisit if:** The problem statement is stress-tested (in Constitution & Strategy, Chat 1) and found to be overstated or incomplete.

---

## 2026-02-28 — Axiom Independence
**Status:** Active
**Domain:** Strategy
**Context:** The initial analysis was organized around the axiom "Optimizes for outcomes, not outrage." The builder clarified they are not committed to this or any slogan.
**Decision:** The project is axiom-agnostic. No slogans, no ideological commitments. Design choices are evaluated instrumentally against the coordination gap problem, not against a normative principle.
**Reasoning:** Axioms close off design space prematurely. "Outcomes over outrage" would have ruled out engagement mechanics, identity-expressive features, and emotional design elements that may be necessary to sustain participation. Staying agnostic keeps the design space open.
**Implications:** Design documents should not reference "outcomes over outrage" as a governing principle. The anti-outrage design choices in the architecture (structured signals, chronological feeds, no reaction counts) remain valid but must now justify themselves instrumentally — "this prevents engagement dynamics from drowning out coordination" — rather than dogmatically.
**Revisit if:** Never. This is a meta-principle about how we make decisions, not a design choice.

---

## 2026-03-07 — Web-First Frontend (Replacing React Native Mobile App)
**Status:** Active
**Domain:** Technical
**Context:** The initial scaffold included a React Native + Expo mobile app targeting iOS. The builder is a solo beginner developer. Mobile development requires managing the Apple Developer Program, Xcode, EAS Build, TestFlight, App Store review, privacy policies, and the React Native toolchain — each a potential multi-day blocker.
**Options considered:** (a) Continue with React Native mobile, (b) Switch to web-first with React, (c) Switch to web-first with plain HTML/CSS/JS, then migrate to React later.
**Decision:** Option (c). Start with plain HTML/CSS/JS served directly from FastAPI. Migrate to React once the fundamentals are comfortable.
**Reasoning:** A website eliminates all App Store overhead. Plain HTML/CSS/JS eliminates the React build toolchain, JSX syntax, and component model — all new concepts for a beginner. The FastAPI backend doesn't care what calls it; the API endpoints work identically regardless of frontend technology. The deliberation platform has no features requiring native mobile capabilities (no camera, GPS, or hardware APIs). A responsive website works on phones through the browser. Starting with vanilla web tech teaches the HTTP request/response cycle, DOM manipulation, and API communication in their simplest form, creating a foundation for React later.
**Implications:** The React Native code in the `mobile/` directory is archived, not deleted — it contains useful patterns (API client structure, component hierarchy). The architecture.md needs updating to reflect the web-first stack. Deployment simplifies to a single Render.com service (FastAPI serving both API and static files). The roadmap phases related to App Store submission, TestFlight, and EAS Build are deferred indefinitely.
**Revisit if:** The platform is validated with real users and there is demand for a native mobile experience, or if a technical co-founder joins who is comfortable with React Native.

---

## 2026-03-07 — Three-Project Claude Structure
**Status:** Active
**Domain:** Strategy
**Context:** Needed to organize the Claude workflow across multiple domains (strategy, development, mechanism design) without overloading any single project's context window or mixing unrelated concerns.
**Options considered:** (a) One project with everything, (b) Separate chats within one project, (c) Three separate projects with distinct files and instructions.
**Decision:** Three separate Claude Projects: Constitution & Strategy, Platform Development, Mechanism Design.
**Reasoning:** Projects carry persistent context (uploaded files + custom instructions) that every new chat inherits. A single project would force every chat to load political theory, code files, and mechanism design papers simultaneously, degrading focus. Separate projects let each conversation start with the right context. The three domains have distinct file needs (Strategy needs the analysis doc; Development needs code files; Mechanism Design needs academic papers) and distinct interaction styles (Strategy thinks together; Development produces blueprints for Claude Code; Mechanism Design produces specifications).
**Implications:** Cross-project communication requires manual effort — decisions made in one project must be communicated to others via updated files or pasted context. The decisions.md file lives primarily in Constitution & Strategy. The mechanism-spec.md bridges Mechanism Design and Platform Development.
**Revisit if:** A future Claude feature enables cross-project file syncing or shared memory across projects.

---

## 2026-03-07 — Hybrid Agentic Workflow (AI Builds, Human Steers)
**Status:** Active
**Domain:** Strategy
**Context:** The initial project setup was heavily learning-oriented, with system instructions focused on teaching the builder line-by-line. The builder identified that this approach makes human learning the bottleneck on progress, when the irreplaceable human contribution is judgment (about governance, mechanisms, legitimacy), not code.
**Options considered:** (a) Learning-first (AI teaches, human implements), (b) Agentic-first (AI implements, human reviews), (c) Hybrid (AI builds by default, teaches on request; human steers and makes judgment calls).
**Decision:** Option (c). AI defaults to producing work products (documents, specifications, implementation blueprints). Human provides judgment on flagged decision points. Teaching happens on request, not by default. Architectural understanding is maintained (human knows WHY the system works this way) even when implementation details are delegated.
**Reasoning:** The builder's strategic and analytical skills are strong. The bottleneck is not understanding Python decorators — it's institutional design, theory of change, and mechanism selection. Time spent on coding tutorials crowds out the conceptual work where the builder has highest leverage. A real technical developer will be brought in to review code/architecture when the project gains traction. Until then, AI-generated code supervised by AI-generated tests is sufficient for an MVP.
**Implications:** System instructions across all projects say "default to doing the work." Platform Development produces blueprints with "CLAUDE CODE INSTRUCTIONS" sections for direct execution. Constitution & Strategy drafts complete documents and flags "DECISION NEEDED" points. Mechanism Design produces complete specifications. The builder's learning is targeted at domain knowledge (Ostrom, Fishkin, mechanism design) and architectural understanding (data model, state machine, auth flow), not implementation syntax.
**Revisit if:** Code quality becomes a blocking issue, or a technical co-founder joins and wants to restructure the development workflow.

---

## 2026-02-28 — Phase-Gated Deliberation Model
**Status:** Active
**Domain:** Mechanism / Strategy
**Context:** Core architectural decision about how deliberation is structured on the platform.
**Decision:** Threads follow a one-directional state machine: OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED → ARCHIVED. Only facilitators can advance phases. Each transition requires a written reason logged to the audit log. Phase gates enforce which actions are available (posts in OPEN/DELIBERATING, proposals in PROPOSING, votes in VOTING, read-only in CLOSED+).
**Reasoning:** Phase-gating prevents outrage-driven shortcuts. You cannot vote without first deliberating. You cannot propose without the thread being in the proposing phase. This forces sequential engagement with the issue before any decision is made. The one-directional constraint prevents facilitators from reopening phases to manipulate outcomes. The mandatory reason for each transition creates facilitator accountability.
**Implications:** The frontend must make the current phase visually prominent. UI elements (post form, proposal form, vote buttons) must appear and disappear based on phase. The audit log must capture phase transitions with facilitator ID and reason. The signal system operates across all phases. The state machine is enforced at the backend level — no frontend-only enforcement.
**Revisit if:** User testing reveals that the linear sequence is too rigid (e.g., deliberation surfaces new information that makes prior proposals obsolete, but the thread can't go back to DELIBERATING).

---

## 2026-02-28 — Structured Signals Instead of Upvotes/Downvotes
**Status:** Active. Partially superseded by "Reactions Permitted on Individual Contributions" (2026-04-09) — the blanket no-reactions rule is narrowed; see that entry.
**Domain:** Mechanism
**Context:** Traditional forums use upvotes/downvotes, which create popularity contests and outrage incentives. The platform needed an alternative that captures richer information about participant sentiment.
**Decision:** Four signal types: support, concern, need_info, block. One signal per user per thread (not per post). Signals are changeable (upsert pattern). Changes are logged to the audit log.
**Reasoning:** Signals on threads (not posts) prevent individual posts from becoming targets of pile-on engagement. The four types capture more information than binary up/down: "I support this direction," "I have concerns," "I need more information before I can judge," and "I believe proceeding would cause serious harm." Block signals are surfaced prominently even as a minority — this protects dissent and ensures minority concerns are visible.
**Implications:** The signal system specification needs further development (see Mechanism Design, Chat 2). Open questions: should signal distributions constrain phase advancement? Should participants see real-time distributions? Should signals be withdrawable (return to no signal)? These are queued for the Mechanism Design project.
**Revisit if:** User testing reveals the four types are confusing, redundant, or insufficient. Or if the distinction between "concern" and "block" proves unclear in practice.

---

## 2026-02-28 — Append-Only Public Audit Log
**Status:** Active
**Domain:** Technical / Governance
**Context:** Transparency is the platform's primary claim to legitimacy. Every significant action must be independently verifiable.
**Decision:** The audit_logs table is append-only in application code. All significant actions produce an entry (phase changes, posts, signals, proposals, votes, allocations). The /api/v1/audit endpoint is public and unauthenticated. Actor identity is stored as UUID (no PII in the log itself).
**Reasoning:** The audit log is what makes the platform's decisions reconstructable. If you can independently verify that every allocation decision matches the deliberation trail, the platform earns trust it can't get any other way. Public access means journalists, researchers, and skeptics can audit the platform without permission. Append-only prevents historical revisionism. The audit log functions as a capture detector — a public, immutable record that makes facilitator or institutional capture visible rather than hidden, not merely an accountability surface after the fact.
**Implications:** The backend must write audit entries for every significant action — this is a hard requirement, not a nice-to-have. Future hardening: PostgreSQL trigger to enforce append-only at the DB level (prevents even admin deletion). The legitimacy test suite ("can you reconstruct a decision from the audit log alone?") validates this property.
**Revisit if:** Privacy regulations require the ability to delete user-associated audit entries (GDPR right to erasure). This would create a tension between transparency and privacy that needs legal analysis.

---

## 2026-02-28 — Identity Tiers
**Status:** Active (updated 2026-04-03 — see also: Thread Creation Tier and Facilitator Request Flow decisions below)
**Domain:** Mechanism / Technical
**Context:** The platform needs Sybil resistance without excessive friction. Different levels of engagement require different levels of trust.
**Decision:** Four tiers: registered (email magic link — can read, cast signals, create threads), participant (manual verification by facilitator — can post, vote, create proposals), facilitator (promoted via web request flow approved by admin — can advance phases, moderate), admin (seeded — can create domains/pools, record allocations, approve facilitator requests).
**Reasoning:** Tiered identity creates a friction gradient: low friction for low-stakes actions (reading, signaling), higher friction for high-stakes actions (voting, proposing). Manual verification by facilitators is the MVP approach to Sybil resistance — imperfect but auditable and human-scale. Email-only registration creates some friction (harder to mass-create accounts than social login) while remaining accessible.
**Implications:** The verification protocol for the participant tier needs specification (see Mechanism Design, Chat 3). The facilitator tier carries significant power and needs accountability mechanisms (see governance charter). The system scales manually to maybe 500 users before verification becomes a bottleneck. Migration path to more scalable identity verification is a post-MVP concern.
**Revisit if:** The Sybil resistance analysis (Mechanism Design, Chat 3) reveals that email-only registration is too weak for even MVP-scale deliberation. Or if manual verification proves too slow to onboard users for a time-sensitive deliberation.

---

## 2026-02-28 — LLM Assistant as Read-Only Research Tool
**Status:** Active
**Domain:** Technical / Strategy
**Context:** LLMs could play many roles on a deliberation platform — from summarizing threads to generating proposals to recommending vote choices.
**Decision:** The LLM is a read-only research assistant, never a deliberation participant. It summarizes, explains, and answers questions from a curated corpus. It never posts in threads, recommends vote choices, generates proposals, or has access to individual vote choices. All LLM outputs are clearly labeled. LLM features are disabled during the VOTING phase. Implementation is deferred to after Phase 4 (first real deliberation validated without LLM).
**Reasoning:** If the LLM influences deliberation outcomes, the platform's legitimacy claim collapses — decisions were made by an algorithm, not by citizens. The read-only constraint preserves the principle that all substantive content is human-generated. Deferring implementation ensures the deliberation process works on its own merit before adding AI assistance.
**Implications:** The llm-integration.md spec is complete but implementation is Phase 5. The frontend must never display LLM-generated content in the thread feed. The audit log must record every LLM call. Facilitators can suppress LLM summaries for a thread if participants report them as misleading.
**Revisit if:** User feedback from Phase 4 indicates that participants want LLM assistance during deliberation, or if the summarization proves too low-quality to be useful.

---

## 2026-02-28 — MVP Scope: Single Healthcare Sub-Issue, Single State
**Status:** Active
**Domain:** Strategy
**Context:** The adversarial analysis warned that launching multi-issue and national "guarantees culture-war capture before the institution has norms or immune systems."
**Decision:** MVP targets one healthcare sub-issue (e.g., prescription drug pricing) in one U.S. state (e.g., Colorado, which has existing legislative momentum on drug pricing). Invite-only beta of 500–2,000 verified residents. Simple preference aggregation (mechanism TBD). One experienced state lobbyist for execution. Public transparency dashboard.
**Reasoning:** Narrow scope prevents culture-war capture, keeps the user base manageable for manual identity verification, and creates a measurable test: did this specific deliberation influence this specific legislative outcome? The healthcare domain is chosen because apparent consensus ("lower costs") dissolves on mechanism (single-payer vs. market reform), making it a genuine test of whether the platform can navigate real disagreement.
**Implications:** The platform architecture should support multiple domains but the MVP only activates one. User recruitment requires partnerships with existing healthcare advocacy groups in the target state. The theory of change must specify how a 500-person deliberation in Colorado connects to legislative action in that state.
**Revisit if:** A different sub-issue or state offers a more tractable initial deployment. Or if the builder identifies a non-healthcare domain with lower stakes for initial testing.

---

## 2026-02-28 — Legal Structure: Single 501(c)(4) for MVP
**Status:** Active
**Domain:** Legal
**Context:** The adversarial analysis identified a likely need for a multi-entity structure (c)(3) + (c)(4) + PAC) at scale, but recommended simplicity for MVP.
**Decision:** Single 501(c)(4) social welfare organization for the MVP phase.
**Reasoning:** A (c)(4) can lobby without limit, which is essential for the execution layer (hiring a lobbyist). It avoids the complexity of coordinating multiple entities. Donors are not tax-deductible, which is a limitation but not a blocker at MVP scale. The structure is simpler to set up and maintain than a multi-entity constellation.
**Implications:** No tax-deductible donations. Must file Form 990 with the IRS. Must register for charitable solicitation in states where funds are raised. Cannot do electioneering (supporting/opposing candidates) beyond a limited amount. The legal compliance memo (Constitution & Strategy, Chat 4) will detail these constraints. Architecture decisions about fund handling must comply with (c)(4) rules.
**Revisit if:** The platform needs to engage in electoral activity (supporting/opposing candidates), which would require a PAC. Or if a major donor requires tax deductibility, which would require a companion (c)(3) for the educational components.

---

## 2026-03-07 — Bring On Technical Developer When Project Gains Traction
**Status:** Active
**Domain:** Strategy
**Context:** The builder is a beginner developer using AI assistance (Claude Code + Claude chat) to build the MVP. Code quality and architectural soundness are managed by AI but not independently verified by a human expert.
**Decision:** Continue with the AI-assisted solo build for now. When the project gains traction (defined as: real users completing real deliberations, or external interest/funding), bring on a technical developer to review and audit the entire codebase and architecture.
**Reasoning:** The MVP phase is about validating the institutional design, not shipping production-quality software. AI-generated code supervised by AI-generated tests is sufficient for an invite-only beta. The cost of a technical hire before validation is premature. The cost of technical debt is manageable if the project is small and the codebase is well-documented.
**Implications:** Code should be kept simple and well-documented so a future developer can understand and refactor it. Architecture decisions should be explicitly recorded (this file). The builder should maintain architectural understanding even if implementation details are delegated to AI.
**Revisit if:** A critical bug or security vulnerability is discovered that AI cannot resolve. Or if a technical co-founder expresses interest in joining.

---

## 2026-04-03 — Thread Creation Lowered to Registered Tier
**Status:** Active
**Domain:** Technical / Mechanism
**Context:** The original design required participant tier (manually verified) to create threads. For MVP testing before a live deliberation, this creates a catch-22: you can't test the thread creation flow without first verifying every tester as a participant, even when the goal is UI testing, not deliberation integrity.
**Options considered:** (a) Keep thread creation at participant tier, (b) Lower to registered tier, (c) Add a separate "proposer" tier between registered and participant.
**Decision:** Option (b). Registered users (email magic link only) can create threads for MVP.
**Reasoning:** The legitimacy-critical actions are voting and posting — those remain at participant tier where Sybil resistance matters. Thread creation is an organizational action (setting up a topic and prompt) rather than a deliberation action. Lowering it to registered tier lets the builder and early testers exercise the full thread setup workflow without a manual verification ceremony. The state machine still prevents voting/posting without participant tier.
**Implications:** Thread creation by unverified users means more noise threads are possible. Mitigation: facilitator controls (phase gating, moderation). This is acceptable at invite-only beta scale. Revisit when the platform opens to public registration.
**Revisit if:** Spam threads become a problem, or when the platform scales beyond invite-only beta.

---

## 2026-04-03 — Facilitator Request Web Flow (Replacing Manual Admin Promotion)
**Status:** Active
**Domain:** Technical / Governance
**Context:** The original design had admins promoting users to facilitator tier via a direct API call with no structured request/approval process. This means no audit trail, no stated reason, and no user-initiated pathway.
**Options considered:** (a) Keep direct admin promotion via API, (b) Build a web-based request/approval flow, (c) Use an out-of-band process (email, Slack) with admin updating the DB.
**Decision:** Option (b). Users submit a facilitator application (reason field, 10–500 chars) via the account page. Admins review and approve/deny via /admin page. Approval automatically promotes the user's tier to FACILITATOR.
**Reasoning:** A structured request flow creates an audit trail (FACILITATOR_REQUEST_SUBMITTED, FACILITATOR_REQUEST_APPROVED/DENIED events in the audit log), makes the facilitator selection process visible, and gives facilitators a documented reason for their appointment. It also prevents the admin from needing direct database access for routine tier promotions, which is a security hygiene improvement.
**Implications:** The FacilitatorRequest model and migration must be deployed before facilitator promotion is possible through the UI. The admin route requires AdminUser dependency — admins are still seeded directly (no web flow for admin promotion). The audit log now captures the full facilitator lifecycle.
**Revisit if:** The facilitator selection process needs more formal criteria or a multi-step review (e.g., community endorsement before admin approval).

---

## 2026-04-09 — Reactions Permitted on Individual Contributions
**Status:** Active. Partially supersedes "Structured Signals Instead of Upvotes/Downvotes" (2026-02-28).
**Domain:** Mechanism / Technical
**Context:** The original no-reactions rule conflated two distinct things: reactions that drive display order (pile-ons, bandwagoning, algorithmic amplification) and reactions that serve as editorial feedback on individual contributions. The annotation system for the wiki requires the second kind. The first kind remains prohibited.
**Options considered:** (a) Maintain the blanket no-reactions rule, (b) Allow reactions on annotations with explicit constraints against ranking use.
**Decision:** Reactions are permitted on annotations. Reaction types are `endorse` and `needs_work` — not upvote/downvote, not like/dislike. Reactions may in the future extend to posts, replies, and proposals. Reactions must never determine display order, filter visibility, boost, bury, or rank content. Chronological ordering remains the only permitted sort for any feed. Reaction counts may be displayed alongside content but must not influence what content is shown or in what order.
**Reasoning:** Distinguishes editorial feedback from engagement-driven amplification. Preserves the architectural commitment against ranking-driven discourse while enabling structured feedback for long-form editorial review.
**Implications:** The annotation system can use endorse/needs_work reactions. Any future feature that uses reaction counts as a sort key, filter, or ranking input should be rejected. CLAUDE.md constraint #4 updated to reflect the new rule.
**Revisit if:** Evidence emerges that even non-ranking reactions produce harmful dynamics in practice.

---

## 2026-04-09 — Inline Annotation System with Generic Target Model
**Status:** Active
**Domain:** Technical / Mechanism
**Context:** Need a way for permissioned reviewers to give in-place feedback on wiki articles, with reactions and replies. Could be built wiki-specific or as a generic annotation layer.
**Options considered:** (a) Wiki-specific annotation tables and routes, (b) Generic target-agnostic annotation system from v1.
**Decision:** Build target-agnostic from v1. The `annotations` table uses `target_type` (wiki|post|proposal|document) and `target_id` so the same backend and frontend serve annotations on any content type. v1 ships on wiki only. Extension to other targets is deferred and requires a separate decision before implementation. Anchoring is text-range based using Hypothesis's open-source libraries (`dom-anchor-text-quote` and friends), with section-level fallback when text anchoring fails.
**Reasoning:** Building target-agnostic from the start costs nothing extra and avoids a future rewrite. Hypothesis's anchoring libraries are well-tested and in production use. Section-level fallback handles the orphan case (anchor text edited out of the document) without losing the annotation.
**Implications:** New `annotator` capability on the user tier system. New `annotations` and `annotation_reactions` tables. New API routes under `/api/v1/annotations`. New frontend module loaded on wiki pages. All annotation actions write to the audit log. Soft deletes only.
**Revisit if:** Text-range anchoring proves too fragile in practice, or the generic target model creates unforeseen complexity.

---

## 2026-04-01 — GitHub Codespaces as Primary Development Environment
**Status:** Active
**Domain:** Technical
**Context:** The builder's 2016 MacBook (Monterey 12.7.6, ~3.66 GB free disk space) cannot support local developer tooling installation. Attempts to install git via Xcode Command Line Tools failed due to macOS version constraints and insufficient disk space. Homebrew installation was blocked by the same CLT dependency. Local development is not viable on current hardware.
**Options considered:** (a) Continue attempting local setup on 2016 MacBook, (b) GitHub Codespaces (browser-based VS Code + Linux terminal), (c) Replit (similar browser-based environment).
**Decision:** GitHub Codespaces as the primary development environment. All tooling (Python, git, Claude Code) runs in the cloud. The local Mac is used only as a browser.
**Reasoning:** Codespaces provides a full Linux environment with git pre-installed, eliminating all local hardware constraints. It integrates directly with the GitHub repository. Claude Code installs in Codespaces with a single curl command. The free tier (120 core-hours/month) is sufficient for solo development at this pace. Codespaces also makes the underlying OS of the local machine irrelevant — a future switch to a new machine has zero impact on the development environment.
**Implications:** All terminal commands in Claude Code instructions must assume a Linux/Codespaces environment. No Homebrew, no Xcode CLT, no macOS-specific tooling. The `.env` file with Supabase credentials must be configured inside the Codespace (never committed to git). Claude Code is installed via `curl -fsSL https://claude.ai/install.sh | bash` once per Codespace. Codespaces auto-suspend after 30 minutes of inactivity — the server must be restarted each session with `uvicorn app.main:app --reload`.
**Revisit if:** Builder acquires a new development machine (Mac Mini M4 under consideration) with sufficient disk space for local tooling. At that point, local development becomes viable and Codespaces becomes optional rather than required.

---

# Pending Decisions

These decisions have been identified as needed but not yet resolved. They are queued for the appropriate project.

| Decision | Domain | Queued For |
|----------|--------|------------|
| MVP voting mechanism (approval, ranked-choice, score, or keep yes/no/abstain) | Mechanism | Mechanism Design, Chat 1 |
| Signal-phase interaction (informational only vs. soft/hard constraint on advancement) | Mechanism | Mechanism Design, Chat 2 |
| Signal visibility (real-time vs. post-phase aggregates) | Mechanism | Mechanism Design, Chat 2 |
| Signal withdrawal (can users return to "no signal"?) | Mechanism | Mechanism Design, Chat 2 |
| Participant verification protocol (what does a facilitator actually verify?) | Mechanism | Mechanism Design, Chat 3 |
| Block signal threshold (at what % do blocks halt proceedings?) | Mechanism / Governance | Mechanism Design, Chat 2 |
| Theory of leverage (how does aggregated preference become political force?) | Strategy | Constitution & Strategy, Chat 1 |
| Facilitator selection, term limits, and accountability process | Governance | Constitution & Strategy, Chat 2 |
| Fork rights (what's forkable, what triggers a fork, what process?) | Governance | Constitution & Strategy, Chat 2 |
| Target state and sub-issue for MVP deployment | Strategy | Constitution & Strategy, Chat 1 |
| Incentive design for sustained participation | Mechanism | Mechanism Design, Chat 4 |
| Deployment architecture (single Render service vs. split) | Technical | Resolved: single Render service (Platform Development, Chat 1) |
