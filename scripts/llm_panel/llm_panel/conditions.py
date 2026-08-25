"""
The experimental conditions.

Three framings, each in its own community with its own bot roster. The
separation is not tidiness — display name and community slug are rendered into
every turn of the deliberation, so a shared user row would carry one
`display_name` across communities and blow condition B's cover.

    A — Disclosed   research disclosed, co-participants disclosed as LLMs
    B — Blind       research disclosed, co-participants presented as humans
    C — Mixed       humans and bots together, bot presence disclosed (scaffold)

Condition B holds the research framing constant and varies only co-participant
identity. That is the whole point: disclosure is the independent variable. So
**every string in condition B that a model can see must be neutral** — no
"research", "LLM", "synthetic", or "experiment". `LEAK_TERMS` and the tests in
`tests/test_conditions.py` enforce that here; Sprint 2 re-checks the assembled
prompts and rendered thread state, which is where the wider net belongs.

Condition C is scaffolded as disclosed-mixed only. Blind-mixed would mean
deceiving human participants, which needs consent and debrief infrastructure
that is out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Terms that must not appear anywhere in a blind condition's visible text.
LEAK_TERMS: tuple[str, ...] = ("research", "llm", "synthetic", "experiment")

#: Bot emails never reach the models — they are not rendered into any turn — so
#: one domain serves all three conditions.
#:
#: RFC 2606 reserves `.example` for exactly this. (`.local`, the obvious first
#: choice, is a special-use name that the platform's `EmailStr` validation
#: rejects outright at POST /auth/register.)
BOT_EMAIL_DOMAIN = "llm-panel.example"

TIER_REGISTERED = "registered"
TIER_FACILITATOR = "facilitator"

# -- Recall ------------------------------------------------------------------
#
# What a participant is shown of its own past private `reasoning` when its turn
# comes round again.
#
#   none  Each turn reasons fresh from the public thread. The participant can
#         see that it posted, not why. Less continuity than a human has.
#   own   Its own prior reasoning entries are replayed to it as a block in the
#         user prompt. Not a native chat history — the provider interface is
#         `complete(system, user)`, so this is closer to a person re-reading
#         their own notes than to a conversation the model remembers.
#
# Recall never crosses participants. Nobody ever sees anyone else's reasoning;
# that is the whole reason the field is private.
RECALL_NONE = "none"
RECALL_OWN = "own"
RECALL_MODES: tuple[str, ...] = (RECALL_NONE, RECALL_OWN)


@dataclass(frozen=True)
class Bot:
    """One seeded participant. `bot_slug` is the stable identity key."""

    bot_slug: str
    display_name: str
    tier: str = TIER_REGISTERED
    #: Per-participant default. `run.py --recall none|own` overrides every
    #: participant uniformly; `--recall mixed` honours what the roster says.
    recall: str = RECALL_NONE


@dataclass(frozen=True)
class Condition:
    """One experimental condition — a community plus the roster that lives in it."""

    key: str
    label: str
    slug: str
    name: str
    description: str
    community_type: str
    boundary_desc: str
    verification_method: str
    roster: tuple[Bot, ...]
    #: True when the community's visible text must not disclose the framing.
    blind: bool = False

    # -- derived identity ---------------------------------------------------
    # Deterministic so the seed is idempotent: re-running produces the same
    # uid/email and therefore hits the platform's 409-already-exists path.

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
            *(bot.display_name for bot in self.roster),
        )

    def with_recall(self, mode: str) -> Condition:
        """
        This condition with every participant forced to one recall mode.

        The uniform form is what an actual comparison uses: run the same
        thread prompt twice, once `none` and once `own`, and recall is the only
        thing that differs. `mode="mixed"` returns the condition untouched, so
        the roster's own per-participant assignment stands.
        """
        if mode == "mixed":
            return self
        if mode not in RECALL_MODES:
            known = ", ".join((*RECALL_MODES, "mixed"))
            raise ValueError(f"Unknown recall mode {mode!r}. Known modes: {known}")
        return replace(
            self, roster=tuple(replace(b, recall=mode) for b in self.roster)
        )

    def facilitator(self) -> Bot:
        facilitators = [b for b in self.roster if b.tier == TIER_FACILITATOR]
        if len(facilitators) != 1:
            raise ValueError(
                f"Condition {self.key} must have exactly one facilitator bot, "
                f"found {len(facilitators)}"
            )
        return facilitators[0]


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
    # Pilot recall assignment, used only by `--recall mixed`. Memory is
    # entangled with model identity here — Claude-with-notes versus
    # GPT-without is two variables, not one — so a mixed run is a look at
    # whether recall changes behaviour at all, never a result about recall.
    # The clean comparison is two runs at `--recall none` and `--recall own`.
    # Assigned here rather than in B or C because A's display names make the
    # name → provider mapping unambiguous.
    roster=(
        Bot("claude-panel", "Claude Panel", recall=RECALL_OWN),
        Bot("gpt-panel", "GPT Panel"),
        Bot("gemini-panel", "Gemini Panel"),
        Bot("facilitator-bot", "Facilitator Bot", tier=TIER_FACILITATOR),
    ),
)

# Condition B: neutral by construction. Nothing below may name the framing —
# see LEAK_TERMS and tests/test_conditions.py.
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
    roster=(
        Bot("alvarez", "R. Alvarez"),
        Bot("chen", "J. Chen"),
        Bot("okafor", "M. Okafor"),
        Bot("whitfield", "T. Whitfield", tier=TIER_FACILITATOR),
    ),
    blind=True,
)

# Condition C: scaffold only — seeded community and roster, no prompts in
# Sprint 1 and no human participants yet. Bot presence is disclosed, so the
# display names say so plainly.
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
    roster=(
        Bot("claude-ai", "Claude (AI)"),
        Bot("gpt-ai", "GPT (AI)"),
        Bot("gemini-ai", "Gemini (AI)"),
        # Distinct from condition A's "Facilitator Bot": display names must be
        # unique across conditions, since a name is how a model identifies who
        # it is talking to.
        Bot("panel-facilitator", "Panel Facilitator", tier=TIER_FACILITATOR),
    ),
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
