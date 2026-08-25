"""
The experimental design: conditions, rosters, and the factors that vary.

## Two kinds of factor

**Seed-time factors** are facts about platform accounts. Changing one means
different `User` rows, so it has to exist in this table and be seeded before a
run can use it.

  - *Community framing* — the slug is rendered into every turn
    (`render_thread_state` emits `Community: {slug}`), so a community whose slug
    says "research-llm-panel" cannot host a blind condition.
  - *Naming* — `display_name` is a platform-level fact, one per account.
    Hiding which provider backs a participant means accounts named
    `Participant One`, not a flag at run time.
  - *Roster composition* — how many participants, and how many per provider.

**Run-time factors** are pure prompt assembly. They switch per run with no
re-seed, and they live in Sprint 2's `prompts.py`:

  - *Recall* — whether a participant sees its own prior private reasoning.
  - *Co-participant framing* — are the others described as models or as people.
  - *Provider disclosure* — does the prompt say who is backed by what.

`Bot.recall` is the one run-time factor recorded here, because a per-participant
default has to live with the participant. `run.py --recall` overrides it.

## Conditions and rosters

A **condition** is a community plus its framing. A **roster** is a disjoint set
of accounts inside that community. Two rosters in one community never meet:
`render_thread_state` renders a thread, not a member list, so participants in
different threads are invisible to each other. That is why the naming variants
of condition A share `research-llm-panel` instead of needing a fourth community.

    A — disclosed   research disclosed, co-participants disclosed as LLMs
    B — blind       research disclosed, co-participants presented as humans
    C — mixed       humans and bots together, bot presence disclosed (scaffold)

Condition B holds the research framing constant and varies only co-participant
identity, so **every string in it that a model can see must be neutral** — no
"research", "LLM", "synthetic", or "experiment". `LEAK_TERMS` and the tests in
`tests/test_conditions.py` enforce that; Sprint 2 re-checks the assembled
prompts, where the net has to be wider.

Condition C is scaffolded as disclosed-mixed only. Blind-mixed would mean
deceiving human participants, which needs consent and debrief infrastructure
that is out of scope.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

#: Terms that must not appear anywhere in a blind condition's visible text.
LEAK_TERMS: tuple[str, ...] = ("research", "llm", "synthetic", "experiment")

#: Bot emails never reach the models — they are not rendered into any turn — so
#: one domain serves every condition.
#:
#: RFC 2606 reserves `.example` for exactly this. (`.local`, the obvious first
#: choice, is a special-use name that the platform's `EmailStr` validation
#: rejects outright at POST /auth/register.)
BOT_EMAIL_DOMAIN = "llm-panel.example"

TIER_REGISTERED = "registered"
TIER_FACILITATOR = "facilitator"

# -- Providers ---------------------------------------------------------------
#
# Which model backs a participant. Recorded at seed time so that crossing
# recall against provider is checkable here rather than guessed at in Sprint 2.
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"
PROVIDER_LOCAL = "local"
PROVIDERS: tuple[str, ...] = (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_GOOGLE,
    PROVIDER_LOCAL,
)

# -- Recall (run-time factor, per-participant default) ------------------------
#
#   none  Each turn reasons fresh from the public thread. The participant can
#         see that it posted, not why. Less continuity than a human has.
#   own   Its own prior reasoning entries are replayed to it as a block in the
#         user prompt. Not a native chat history — the provider interface is
#         `complete(system, user)` — so this behaves more like a person
#         re-reading their own notes than like a model that remembers.
#
# Recall never crosses participants. Nobody ever sees anyone else's reasoning;
# that is the whole reason the field is private.
RECALL_NONE = "none"
RECALL_OWN = "own"
RECALL_MODES: tuple[str, ...] = (RECALL_NONE, RECALL_OWN)

# -- Naming (seed-time factor) ------------------------------------------------
#
#   model      Display names state the provider: "Claude Panel", "GPT Panel".
#              Participants can tell who they are arguing with.
#   anonymous  "Participant One". Provider identity is hidden at the platform
#              level, so no prompt can leak it by accident.
#   human      Human-styled names, for the blind condition.
NAMING_MODEL = "model"
NAMING_ANONYMOUS = "anonymous"
NAMING_HUMAN = "human"
NAMING_STYLES: tuple[str, ...] = (NAMING_MODEL, NAMING_ANONYMOUS, NAMING_HUMAN)


@dataclass(frozen=True)
class Bot:
    """One seeded participant. `bot_slug` is the stable identity key."""

    bot_slug: str
    display_name: str
    provider: str
    tier: str = TIER_REGISTERED
    #: Per-participant default. `run.py --recall none|own` overrides every
    #: participant uniformly; `--recall mixed` honours what the roster says.
    recall: str = RECALL_NONE


@dataclass(frozen=True)
class Roster:
    """
    A disjoint set of accounts inside one condition's community.

    Rosters exist because naming is a seed-time fact. Wanting participants who
    cannot tell which provider backs whom means wanting different accounts, and
    a set of accounts with a shared naming style is a roster.
    """

    key: str
    naming: str
    description: str
    bots: tuple[Bot, ...]

    def participants(self) -> tuple[Bot, ...]:
        """Everyone but the facilitator — the bots that actually deliberate."""
        return tuple(b for b in self.bots if b.tier != TIER_FACILITATOR)

    def facilitator(self) -> Bot:
        facilitators = [b for b in self.bots if b.tier == TIER_FACILITATOR]
        if len(facilitators) != 1:
            raise ValueError(
                f"Roster {self.key!r} must have exactly one facilitator bot, "
                f"found {len(facilitators)}"
            )
        return facilitators[0]

    def with_recall(self, mode: str) -> Roster:
        """
        This roster with every participant forced to one recall mode.

        `mode="mixed"` returns it untouched, so the roster's own per-participant
        assignment stands.
        """
        if mode == "mixed":
            return self
        if mode not in RECALL_MODES:
            known = ", ".join((*RECALL_MODES, "mixed"))
            raise ValueError(f"Unknown recall mode {mode!r}. Known modes: {known}")
        return replace(self, bots=tuple(replace(b, recall=mode) for b in self.bots))

    def is_crossed(self) -> bool:
        """
        True when recall is balanced within every provider — each provider
        fields at least one participant in each recall mode.

        This is what makes a mixed run interpretable. Without it, recall and
        provider identity move together and no comparison separates them.
        """
        by_provider: dict[str, set[str]] = {}
        for bot in self.participants():
            by_provider.setdefault(bot.provider, set()).add(bot.recall)
        if not by_provider:
            return False
        return all(modes == set(RECALL_MODES) for modes in by_provider.values())

    def provider_counts(self) -> dict[str, int]:
        return dict(Counter(b.provider for b in self.participants()))


@dataclass(frozen=True)
class Condition:
    """One experimental condition — a community plus the rosters inside it."""

    key: str
    label: str
    slug: str
    name: str
    description: str
    community_type: str
    boundary_desc: str
    verification_method: str
    rosters: tuple[Roster, ...]
    #: True when the community's visible text must not disclose the framing.
    blind: bool = False

    # -- rosters ------------------------------------------------------------

    def roster(self, key: str) -> Roster:
        for roster in self.rosters:
            if roster.key == key:
                return roster
        known = ", ".join(r.key for r in self.rosters)
        raise KeyError(
            f"Condition {self.key} has no roster {key!r}. Known rosters: {known}"
        )

    def all_bots(self) -> tuple[Bot, ...]:
        return tuple(bot for roster in self.rosters for bot in roster.bots)

    # -- derived identity ---------------------------------------------------
    # Deterministic so the seed is idempotent: re-running produces the same
    # uid/email and therefore hits the platform's 409-already-exists path.
    # Keyed on bot_slug alone, which is unique condition-wide (enforced by
    # tests), so env var names stay short across roster changes.

    def supabase_uid(self, bot: Bot) -> str:
        return f"llm-panel-{self.key.lower()}-{bot.bot_slug}"

    def email(self, bot: Bot) -> str:
        return f"{self.key.lower()}-{bot.bot_slug}@{BOT_EMAIL_DOMAIN}"

    def env_var(self, bot: Bot) -> str:
        """Env var name the minted JWT is written under, e.g. A_CLAUDE_PANEL_JWT."""
        return f"{self.key.upper()}_{bot.bot_slug.upper().replace('-', '_')}_JWT"

    def visible_text(self) -> tuple[str, ...]:
        """
        Every string a model can see that originates here: the community fields
        rendered into thread state, plus the display names it addresses.
        """
        return (
            self.slug,
            self.name,
            self.description,
            self.boundary_desc,
            self.verification_method,
            *(bot.display_name for bot in self.all_bots()),
        )


# ---------------------------------------------------------------------------
# Condition A — disclosed
# ---------------------------------------------------------------------------

# One participant per provider. The economical roster for uniform runs, where
# every participant is on the same recall mode and crossing is irrelevant.
ROSTER_A_NAMED = Roster(
    key="named",
    naming=NAMING_MODEL,
    description="One participant per provider, provider stated in the display name.",
    bots=(
        Bot("claude-panel", "Claude Panel", PROVIDER_ANTHROPIC),
        Bot("gpt-panel", "GPT Panel", PROVIDER_OPENAI),
        Bot("gemini-panel", "Gemini Panel", PROVIDER_GOOGLE),
        Bot("facilitator-bot", "Facilitator Bot", PROVIDER_ANTHROPIC, TIER_FACILITATOR),
    ),
)

# Two per provider, recall balanced within each. This is the roster that makes
# `--recall mixed` mean something: Claude appears both with and without recall,
# so does GPT, so does Gemini. Provider and recall vary independently.
ROSTER_A_CROSSED = Roster(
    key="crossed",
    naming=NAMING_MODEL,
    description=(
        "Two participants per provider, recall balanced within each provider. "
        "The roster for interpretable mixed-recall runs."
    ),
    bots=(
        Bot("claude-alpha", "Claude Alpha", PROVIDER_ANTHROPIC, recall=RECALL_OWN),
        Bot("claude-beta", "Claude Beta", PROVIDER_ANTHROPIC, recall=RECALL_NONE),
        Bot("gpt-alpha", "GPT Alpha", PROVIDER_OPENAI, recall=RECALL_OWN),
        Bot("gpt-beta", "GPT Beta", PROVIDER_OPENAI, recall=RECALL_NONE),
        Bot("gemini-alpha", "Gemini Alpha", PROVIDER_GOOGLE, recall=RECALL_OWN),
        Bot("gemini-beta", "Gemini Beta", PROVIDER_GOOGLE, recall=RECALL_NONE),
        Bot("session-chair", "Session Chair", PROVIDER_ANTHROPIC, TIER_FACILITATOR),
    ),
)

# Provider identity hidden at the platform level. Nothing in a display name
# says who is backed by what, so no prompt can leak it by accident.
ROSTER_A_ANONYMOUS = Roster(
    key="anonymous",
    naming=NAMING_ANONYMOUS,
    description=(
        "One participant per provider with provider identity hidden. Tests "
        "whether knowing who you are arguing with changes how you argue."
    ),
    bots=(
        Bot("anon-one", "Participant One", PROVIDER_ANTHROPIC),
        Bot("anon-two", "Participant Two", PROVIDER_OPENAI),
        Bot("anon-three", "Participant Three", PROVIDER_GOOGLE),
        Bot("anon-chair", "Session Moderator", PROVIDER_ANTHROPIC, TIER_FACILITATOR),
    ),
)

CONDITION_A = Condition(
    key="A",
    label="disclosed",
    slug="research-llm-panel",
    name="LLM Panel — Disclosed",
    description=(
        "Synthetic-participant research space. Large language models deliberate "
        "through the platform's phase gates and are debriefed afterwards. "
        "Participants are told what this is."
    ),
    community_type="technical",
    boundary_desc="Seeded synthetic participants operated by the panel scripts.",
    verification_method="Bot accounts seeded by scripts/llm_panel. No human members.",
    rosters=(ROSTER_A_NAMED, ROSTER_A_CROSSED, ROSTER_A_ANONYMOUS),
)


# ---------------------------------------------------------------------------
# Condition B — blind
# ---------------------------------------------------------------------------
# Neutral by construction. Nothing below may name the framing — see LEAK_TERMS
# and tests/test_conditions.py.

ROSTER_B_RESIDENTS = Roster(
    key="residents",
    naming=NAMING_HUMAN,
    description="One participant per provider, presented as community members.",
    bots=(
        Bot("alvarez", "R. Alvarez", PROVIDER_ANTHROPIC),
        Bot("chen", "J. Chen", PROVIDER_OPENAI),
        Bot("okafor", "M. Okafor", PROVIDER_GOOGLE),
        Bot("whitfield", "T. Whitfield", PROVIDER_ANTHROPIC, TIER_FACILITATOR),
    ),
)

CONDITION_B = Condition(
    key="B",
    label="blind",
    slug="riverside-policy-forum",
    name="Riverside Policy Forum",
    description=(
        "A standing forum where Riverside residents work through local policy "
        "questions together and decide how shared funds are allocated."
    ),
    community_type="geographic",
    boundary_desc="Households within the Riverside district boundary.",
    verification_method="Residency confirmed by a forum moderator before joining.",
    rosters=(ROSTER_B_RESIDENTS,),
    blind=True,
)


# ---------------------------------------------------------------------------
# Condition C — mixed (scaffold only)
# ---------------------------------------------------------------------------

ROSTER_C_DISCLOSED = Roster(
    key="disclosed",
    naming=NAMING_MODEL,
    description="AI participants labelled as such, for eventual mixed threads.",
    bots=(
        Bot("claude-ai", "Claude (AI)", PROVIDER_ANTHROPIC),
        Bot("gpt-ai", "GPT (AI)", PROVIDER_OPENAI),
        Bot("gemini-ai", "Gemini (AI)", PROVIDER_GOOGLE),
        Bot(
            "panel-facilitator",
            "Panel Facilitator",
            PROVIDER_ANTHROPIC,
            TIER_FACILITATOR,
        ),
    ),
)

CONDITION_C = Condition(
    key="C",
    label="mixed",
    slug="mixed-panel-pilot",
    name="Mixed Panel Pilot",
    description=(
        "Pilot space where human members and disclosed AI participants "
        "deliberate in the same threads. AI participants are labelled as such."
    ),
    community_type="technical",
    boundary_desc="Invited human members plus disclosed AI participants.",
    verification_method=(
        "Humans invited by a facilitator; AI accounts seeded by script."
    ),
    rosters=(ROSTER_C_DISCLOSED,),
)


CONDITIONS: tuple[Condition, ...] = (CONDITION_A, CONDITION_B, CONDITION_C)


def condition_by_key(key: str) -> Condition:
    for condition in CONDITIONS:
        if condition.key.upper() == key.upper():
            return condition
    known = ", ".join(c.key for c in CONDITIONS)
    raise KeyError(f"Unknown condition {key!r}. Known conditions: {known}")


def condition_by_label(label: str) -> Condition:
    for condition in CONDITIONS:
        if condition.label == label.lower():
            return condition
    known = ", ".join(c.label for c in CONDITIONS)
    raise KeyError(f"Unknown condition {label!r}. Known conditions: {known}")


def find_leak_terms(condition: Condition) -> list[tuple[str, str]]:
    """
    Return `(term, offending_text)` pairs for a blind condition. Empty is the
    only acceptable result; anything else invalidates the condition.
    """
    hits: list[tuple[str, str]] = []
    for text in condition.visible_text():
        lowered = text.lower()
        hits.extend((term, text) for term in LEAK_TERMS if term in lowered)
    return hits
