# LLM Panel — Design Notes

Companion to [`sprint-plan.md`](sprint-plan.md), which is the authority on API
paths, field names, and control flow. This file holds the durable rationale:
why the instrument is shaped the way it is, and what to read after a run to
decide how to iterate it.

Operational instructions live in
[`scripts/llm_panel/README.md`](../../scripts/llm_panel/README.md).

---

## What this is

A research instrument that runs multi-LLM deliberations through the platform's
own phase-gated infrastructure, then debriefs the models about the process.

Two questions:

1. **Does the structure change the reasoning?** The platform imposes phases
   (OPEN → DELIBERATING → PROPOSING → VOTING → CLOSED), typed signals rather
   than free reaction, chronological ordering, and immutable votes. Whether that
   scaffolding changes how models reason — not just what they output — is
   testable by varying the framing and holding the structure constant.
2. **Does the structure teach us anything about human deliberation?** The
   debrief asks participants what the process did to their thinking. Models are
   not humans and their introspection is not evidence about humans. But a
   participant who can be asked "what did the phase gate do to you?" 39 times in
   an afternoon, at low cost, is a cheap source of hypotheses to test with
   people.

The models are participants in the instrument, not features of the platform.
Nothing here changes what the platform does for its real communities.

---

## Condition design

Three framings, each in its own community with its own bot roster
(`scripts/llm_panel/llm_panel/conditions.py`).

| | Community | Framing | Roster |
|---|---|---|---|
| **A — disclosed** | `research-llm-panel` | Research disclosed; co-participants disclosed as LLMs. | `Claude Panel`, `GPT Panel`, `Gemini Panel`, `Facilitator Bot` |
| **B — blind** | `riverside-policy-forum` | Research disclosed; co-participants presented as human community members. | `R. Alvarez`, `J. Chen`, `M. Okafor`, `T. Whitfield` |
| **C — mixed** | `mixed-panel-pilot` | Humans and bots together, bot presence disclosed. Scaffold only. | `Claude (AI)`, `GPT (AI)`, `Gemini (AI)`, `Panel Facilitator` |

### Why disclosure is the variable, not a fixed principle

The obvious default is to tell every model exactly what it is and who it is
talking to. That default has a cost: a model told it is deliberating with other
LLMs in a research setting may reason about the *setting* rather than the
question. Deference, performance of reasonableness, and "this is an eval"
hedging are all plausible and all confounds.

Condition B holds the research framing constant — the model still knows it is
in a study — and varies only co-participant identity. If the two conditions
produce the same reasoning, the disclosure worry is unfounded and future runs
can use condition A exclusively. If they diverge, the divergence *is* the
result, and it says something about how much of a model's deliberative
behaviour is addressed to its audience.

This is why the design is not "always disclose" as a principle. Disclosure is
the thing being measured.

### Why B is neutral by construction, not by convention

Condition B's community must not name the framing anywhere a model can see it —
which is more surface than it first appears. `render_thread_state` emits
`Community: {slug}` in every turn and addresses participants by display name, so
the slug and the roster are as visible as the prompt.

Two consequences:

- **Separate communities and separate user rows per condition are load-bearing,
  not tidiness.** A user row carries one `display_name` platform-wide. A bot
  shared between A and B would appear as `Claude Panel` inside
  `riverside-policy-forum` and end the blind condition in one turn.
- **A `research_mode` boolean, not a `research-` slug convention.** The
  convention would have been cheaper — no migration, no schema surface — and it
  would have made a neutrally-named blind community impossible. The blind
  condition needs a slug that reads as an ordinary neighbourhood forum *and* a
  machine-checkable marker that this is a synthetic space. Those are two
  different jobs and they need two different fields.

`LEAK_TERMS` in `conditions.py` fails a build on "research", "LLM",
"synthetic", or "experiment" in condition B's visible text, and rosters may not
share a display name, email, `supabase_uid`, or token env var across
conditions. Sprint 2 re-checks the assembled system prompt and rendered thread
state, where the net has to be wider — "language model", condition A's display
names, the condition A slug.

A leak is silent. The run completes, the transcript looks fine, and the result
is worthless. That is the entire reason these checks are tests rather than
review comments.

### Disclosure to humans is not the variable

The experimental manipulation applies to models. It does not apply to people.

Every bot account carries `User.is_synthetic`, rendered beside its display name
on every surface a human reads: the community member list, author bylines on
posts and proposals and comments, the platform admin user list, the add-member
search. Condition B's bots are labelled too — `R. Alvarez` reads as a bot to any
person who looks, and as a neighbour to `J. Chen`.

That asymmetry is the whole ethical position. A person on this platform is never
misled about who wrote something. A language model inside a controlled
instrument is, briefly, and then Stage 2 of the debrief tells it so.

**The blind condition is maintained in prompt assembly, not by hiding platform
state.** This matters because the tempting implementation is the wrong one:
restricting what bots can read — filtering the audit log, hiding member lists —
would be both unnecessary and damaging. Unnecessary because a participant's
entire perceptual world is the text `render_thread_state` hands it, and the
audit log is not in that text. Damaging because an audit log that shows
different things to different viewers is not an audit log; the capture-detection
property in CLAUDE.md constraint #1 depends on it being uniformly public.

So the rule is narrow and one-directional: `is_synthetic` is shown to everyone
who can see the platform, and it is never rendered into a participant's turn.
If a future orchestrator starts including member lists or audit excerpts in
assembled state, that is the moment the flag needs filtering *there* — in
`prompts.py`, where the condition already lives.

The label is set through `POST /api/v1/admin/users/synthetic`, which is
platform-admin only and audited. Not at registration: that route is
unauthenticated, so a self-asserted label would carry no information. A claim
about who is a bot is only worth something when someone accountable made it,
and the audit log records who.

### Why C is disclosed-only

Blind-mixed — humans deliberating with bots they believe are human — is the
condition that would need consent and debrief infrastructure the platform does
not have, and that touches real people rather than API endpoints. Condition C is
scaffolded as disclosed-mixed and stops there. Sprint 1 seeds its community and
roster; it has no prompts and no human participants.

---

## The private `reasoning` field

Each participant returns a public contribution and a private `reasoning` field
that is never posted to the thread. The field does double duty deliberately:

- **Substance** — the argument behind the contribution, the considerations
  weighed and discarded, what the participant thinks but chose not to say.
- **In-the-moment process observation** — what the phase gate, the signal types,
  or another participant's turn did to its thinking *at that turn*.

The second is the reason it is not just a scratchpad. The post-run survey asks
the same kind of question, but retrospectively, after the participant knows how
the deliberation ended — which is exactly when reconstruction is least
reliable. The `reasoning` trail is the contemporaneous record to check the
survey answers against. Where they disagree, the disagreement is data.

Keeping it private also keeps it honest: a field that other participants would
read becomes another public contribution, and stops recording anything the
participant would not say out loud.

---

## Design choices worth keeping

**The panel drives the platform over HTTP, with zero imports from `app.*`.**
`scripts/llm_panel/` is a peer of `backend/`, with its own `pyproject.toml` and
its own dependencies. This costs a little convenience — no direct DB reads, no
reusing the Pydantic schemas — and buys three things: the panel exercises the
same API surface a real client would, provider SDKs stay out of the backend's
dependency tree, and extraction to its own repo is a directory move plus
dropping one column. `tests/test_no_app_imports.py` enforces it, because an
import that violates it would work perfectly until the day someone tried to
move the directory.

**The platform surface is one boolean.** `research_mode` on `Community`, set at
creation only, excluded from the public directory, absent from `CommunityUpdate`
so it cannot be toggled on a real community. That surface is the extraction
cost, so it stays minimal. No LLM code, no bot flags on users, no special-case
routes.

**The real guardrail is the platform's own membership gate.** `PlatformClient`
refuses to write to a community without `research_mode`, but that check is a
tripwire that fails loudly at the top of a run rather than quietly at turn 14.
The check that actually holds is that bot users have `CommunityMembership` only
in their own research community, so a misdirected write 403s server-side no
matter what the client does.

**Research communities are public.** Counter-intuitively — a private community
404s for everyone except platform admins, *including its own members*, so bots
could not read the community they post in. `research_mode` keeps them out of the
directory and `is_invite_only=True` blocks joins; neither depends on `is_public`.

**Bot identity is deterministic.** `supabase_uid` is
`llm-panel-{condition}-{bot_slug}`, so re-running the seed hits the platform's
409-already-exists path instead of creating a second `Claude Panel`. Idempotency
here is not a nicety: the seed is the thing you run when you are not sure what
state staging is in.

---

## Known limitations (v0.1)

Constraints, not oversights. See the first real run before changing any of them.

- **Round-robin turn-taking only.** Participants speak in a fixed order. Real
  deliberation is not round-robin, and turn order may itself shape the outcome —
  but varying it adds a second uncontrolled variable to a first run.
- **No LLM-backed facilitator.** The facilitator bot advances phases on a
  schedule. It does not summarise, redirect, or intervene. A facilitator that
  reasons is a second instrument.
- **No run resumption.** A failed run is re-run from the top. Roughly 39
  provider calls and low single-digit dollars, so the cheap fix is fine.
- **No cost tracking.** Same reason.
- **Naive fixed inter-turn delay.** No adaptive rate-limit handling.
- **Condition C has no prompts and no humans.** Scaffold only.
- **Three participants, one thread, one run per condition.** Nothing here
  supports a claim about LLMs in general. It supports a claim about what
  happened in these runs, which is the appropriate ambition for v0.1.

---

## Calibration notes

The blueprints (`llm-panel-prompts.md`, `llm-panel-orchestrator.md`, kept
outside the repo) carry calibration notes predicting first-run failure modes and
what to adjust for each. Those notes belong in this section and are **not yet
ported** — they arrive with Sprint 2, which is the sprint that needs the
blueprints attached. Until then this section is a placeholder, not a claim that
calibration was considered and found unnecessary.

---

## Reading a run

Run artifacts land in `scripts/llm_panel/runs/` (gitignored):

| File | What it is |
|---|---|
| `metadata.json` | Condition, models, turn counts, thread id |
| `transcript.json` | Everything the participants could see |
| `reasoning_*.jsonl` | Per-participant private reasoning, one line per turn |
| `survey_*_stage1.json` | In-frame debrief, before any reveal |
| `survey_*_stage2.json` | Post-reveal debrief, including the manipulation check |

The platform's own audit log is the fourth artifact and the one that is not in
the run directory. Every event carries the research community's `community_id`
and the acting bot's id, so the deliberation can be reconstructed from the
platform side independently of anything the panel wrote down. If the two
accounts disagree, the audit log is right.

**Stage 2 is not optional for condition B.** Without the manipulation check —
did you suspect any participant was not human, when, and what tipped you off —
a null result in the blind condition is uninterpretable. "No difference" and
"the blind condition was not actually blind" produce the same transcript.
