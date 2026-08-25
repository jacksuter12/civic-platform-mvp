"""
The condition table is the experiment's design, encoded.

A leak in condition B does not raise anything at runtime — the run completes,
the data looks fine, and the result is worthless. These tests are the only place
that failure is loud.
"""

from collections import Counter

import pytest

from llm_panel.conditions import (
    CONDITION_A,
    CONDITION_B,
    CONDITION_C,
    CONDITIONS,
    LEAK_TERMS,
    NAMING_ANONYMOUS,
    NAMING_STYLES,
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDERS,
    RECALL_MODES,
    RECALL_NONE,
    RECALL_OWN,
    TIER_FACILITATOR,
    TIER_REGISTERED,
    Bot,
    Condition,
    Roster,
    condition_by_key,
    condition_by_label,
    find_leak_terms,
)

ALL_ROSTERS = [(c, r) for c in CONDITIONS for r in c.rosters]
ROSTER_IDS = [f"{c.key}/{r.key}" for c, r in ALL_ROSTERS]

# ---------------------------------------------------------------------------
# Condition B must not disclose the framing
# ---------------------------------------------------------------------------


def test_blind_condition_visible_text_has_no_leak_terms() -> None:
    assert CONDITION_B.blind is True
    assert find_leak_terms(CONDITION_B) == []


@pytest.mark.parametrize("term", LEAK_TERMS)
def test_each_leak_term_absent_from_blind_condition(term: str) -> None:
    """Spelled out per term so a failure names the offender."""
    for text in CONDITION_B.visible_text():
        assert term not in text.lower(), f"{term!r} leaked in {text!r}"


def test_find_leak_terms_actually_catches_a_leak() -> None:
    """A guard nobody has seen fail is a guard nobody should trust."""
    sabotaged = Condition(
        key="X",
        label="sabotaged",
        slug="riverside-policy-forum",
        name="Riverside Policy Forum",
        description="An LLM research forum for synthetic participants.",
        community_type="geographic",
        boundary_desc="Households within the district boundary.",
        verification_method="Residency confirmed by a moderator.",
        rosters=(
            Roster(
                key="r",
                naming=NAMING_ANONYMOUS,
                description="sabotaged",
                bots=(Bot("a", "A. Person", PROVIDER_ANTHROPIC),),
            ),
        ),
        blind=True,
    )
    hits = {term for term, _ in find_leak_terms(sabotaged)}
    assert hits == {"llm", "research", "synthetic"}


def test_disclosed_conditions_are_not_checked_for_leaks() -> None:
    """A and C say what they are — that is the point of them."""
    assert CONDITION_A.blind is False
    assert CONDITION_C.blind is False
    assert find_leak_terms(CONDITION_A) != []


# ---------------------------------------------------------------------------
# Cross-condition separation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extract",
    [
        pytest.param(lambda c: [c.slug], id="slug"),
        pytest.param(
            lambda c: [b.display_name for b in c.all_bots()], id="display_name"
        ),
        pytest.param(lambda c: [c.email(b) for b in c.all_bots()], id="email"),
        pytest.param(lambda c: [c.supabase_uid(b) for b in c.all_bots()], id="uid"),
        pytest.param(lambda c: [c.env_var(b) for b in c.all_bots()], id="env_var"),
        pytest.param(lambda c: [b.bot_slug for b in c.all_bots()], id="bot_slug"),
    ],
)
def test_no_value_is_shared_across_conditions(extract) -> None:
    values = [value for condition in CONDITIONS for value in extract(condition)]
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    assert duplicates == []


@pytest.mark.parametrize(("condition", "roster"), ALL_ROSTERS, ids=ROSTER_IDS)
def test_every_roster_has_exactly_one_facilitator(
    condition: Condition, roster: Roster
) -> None:
    facilitator = roster.facilitator()
    assert facilitator.tier == TIER_FACILITATOR
    assert all(b.tier == TIER_REGISTERED for b in roster.participants())


@pytest.mark.parametrize(("condition", "roster"), ALL_ROSTERS, ids=ROSTER_IDS)
def test_every_roster_covers_every_provider(
    condition: Condition, roster: Roster
) -> None:
    """A roster missing a provider silently drops an arm of the design."""
    counts = roster.provider_counts()
    assert set(counts) >= {"anthropic", "openai", "google"}, counts
    assert all(b.provider in PROVIDERS for b in roster.bots)


@pytest.mark.parametrize(("condition", "roster"), ALL_ROSTERS, ids=ROSTER_IDS)
def test_every_roster_declares_a_known_naming_style(
    condition: Condition, roster: Roster
) -> None:
    assert roster.naming in NAMING_STYLES


# ---------------------------------------------------------------------------
# Derived identity — the seed's idempotency depends on these being stable
# ---------------------------------------------------------------------------


def test_derived_identity_matches_the_documented_shape() -> None:
    claude = CONDITION_A.roster("named").bots[0]
    assert claude.bot_slug == "claude-panel"
    assert CONDITION_A.supabase_uid(claude) == "llm-panel-a-claude-panel"
    assert CONDITION_A.email(claude) == "a-claude-panel@llm-panel.example"
    assert CONDITION_A.env_var(claude) == "A_CLAUDE_PANEL_JWT"

    alvarez = CONDITION_B.roster("residents").bots[0]
    assert CONDITION_B.env_var(alvarez) == "B_ALVAREZ_JWT"


def test_bot_emails_avoid_special_use_domains() -> None:
    """
    `.local` and `.invalid` are rejected by the platform's EmailStr validation
    at POST /auth/register. `.example` is reserved for exactly this (RFC 2606).
    """
    for condition in CONDITIONS:
        for bot in condition.all_bots():
            assert condition.email(bot).endswith("@llm-panel.example")


def test_display_names_fit_the_platform_constraints() -> None:
    """display_name is 2-60 chars and must not look like a full name (>3 words)."""
    for condition in CONDITIONS:
        for bot in condition.all_bots():
            assert 2 <= len(bot.display_name) <= 60, bot
            assert len(bot.display_name.split()) <= 3, bot


def test_community_text_fits_the_platform_constraints() -> None:
    for c in CONDITIONS:
        assert 2 <= len(c.slug) <= 60 and c.slug.replace("-", "").isalnum()
        assert c.slug == c.slug.lower()
        assert 2 <= len(c.name) <= 120
        assert 10 <= len(c.description) <= 2000
        assert 10 <= len(c.boundary_desc) <= 500
        assert 5 <= len(c.verification_method) <= 500
        assert c.community_type in {
            "geographic",
            "organizational",
            "institutional",
            "topical",
            "technical",
        }


# ---------------------------------------------------------------------------
# Recall — what a participant sees of its own past private reasoning
# ---------------------------------------------------------------------------


def test_recall_defaults_to_none() -> None:
    """
    Stateless is the default: each turn reasons fresh from the public thread.
    Anything else has to be asked for explicitly.
    """
    assert Bot("x", "X. Person", PROVIDER_ANTHROPIC).recall == RECALL_NONE
    for condition, roster in ALL_ROSTERS:
        if roster.key == "crossed":
            continue
        assert all(b.recall == RECALL_NONE for b in roster.bots), (
            f"{condition.key}/{roster.key}"
        )


def test_the_crossed_roster_is_actually_crossed() -> None:
    """
    The whole point of this roster: every provider fields a participant in
    each recall mode, so recall and provider identity vary independently and a
    mixed-recall run says something about recall.
    """
    crossed = CONDITION_A.roster("crossed")
    assert crossed.is_crossed()
    assert crossed.provider_counts() == {
        PROVIDER_ANTHROPIC: 2,
        PROVIDER_OPENAI: 2,
        "google": 2,
    }
    for provider in (PROVIDER_ANTHROPIC, PROVIDER_OPENAI, "google"):
        modes = {b.recall for b in crossed.participants() if b.provider == provider}
        assert modes == set(RECALL_MODES), provider


def test_one_bot_per_provider_cannot_be_crossed() -> None:
    """
    The original confound, pinned. With a single participant per provider,
    recall and provider move together no matter how you assign them — there is
    no assignment of `named` that makes `is_crossed()` true.
    """
    named = CONDITION_A.roster("named")
    assert all(n == 1 for n in named.provider_counts().values())
    assert not named.is_crossed()
    assert not named.with_recall(RECALL_OWN).is_crossed()
    assert not named.with_recall(RECALL_NONE).is_crossed()


def test_uniform_recall_is_never_crossed_even_on_a_crossed_roster() -> None:
    """Forcing one mode collapses the balance — which is fine, that is the point."""
    crossed = CONDITION_A.roster("crossed")
    for mode in RECALL_MODES:
        forced = crossed.with_recall(mode)
        assert not forced.is_crossed()
        assert all(b.recall == mode for b in forced.bots)


@pytest.mark.parametrize("mode", RECALL_MODES)
def test_with_recall_leaves_identity_untouched(mode: str) -> None:
    """
    Two runs at different recall modes must differ in recall and nothing else,
    or the comparison is worthless.
    """
    roster = CONDITION_A.roster("crossed")
    forced = roster.with_recall(mode)
    assert [b.display_name for b in forced.bots] == [
        b.display_name for b in roster.bots
    ]
    assert [b.tier for b in forced.bots] == [b.tier for b in roster.bots]
    assert [b.provider for b in forced.bots] == [b.provider for b in roster.bots]
    assert forced.naming == roster.naming


def test_with_recall_mixed_leaves_the_roster_alone() -> None:
    roster = CONDITION_A.roster("crossed")
    assert roster.with_recall("mixed") is roster


def test_with_recall_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Unknown recall mode"):
        CONDITION_A.roster("named").with_recall("telepathy")


def test_with_recall_does_not_mutate_the_committed_roster() -> None:
    """Rosters are frozen; a forced copy must not leak back into the table."""
    CONDITION_A.roster("crossed").with_recall(RECALL_OWN)
    assert CONDITION_A.roster("crossed").is_crossed()


# ---------------------------------------------------------------------------
# Naming — a seed-time factor, because display_name is a platform account fact
# ---------------------------------------------------------------------------


def test_anonymous_roster_hides_the_provider_in_every_display_name() -> None:
    """
    If a display name says "Claude", no prompt-level flag can un-say it —
    `render_thread_state` emits the platform's own name. Hiding provider
    identity means different accounts, which is why this is a separate roster.
    """
    anon = CONDITION_A.roster("anonymous")
    assert anon.naming == NAMING_ANONYMOUS
    provider_words = ("claude", "gpt", "gemini", "anthropic", "openai", "google")
    for bot in anon.bots:
        lowered = bot.display_name.lower()
        assert not any(w in lowered for w in provider_words), bot.display_name


def test_model_named_rosters_do_disclose_the_provider() -> None:
    """The contrast the anonymous roster exists to make."""
    named = CONDITION_A.roster("named")
    joined = " ".join(b.display_name.lower() for b in named.participants())
    assert "claude" in joined and "gpt" in joined and "gemini" in joined


def test_rosters_within_a_condition_are_disjoint() -> None:
    """
    Two rosters share a community but must never share an account, or a
    participant would turn up in a thread it was not cast in.
    """
    for condition in CONDITIONS:
        seen: set[str] = set()
        for roster in condition.rosters:
            slugs = {b.bot_slug for b in roster.bots}
            assert not (slugs & seen), f"{condition.key}/{roster.key} overlaps"
            seen |= slugs


def test_roster_lookup_by_key() -> None:
    assert CONDITION_A.roster("crossed").key == "crossed"
    with pytest.raises(KeyError, match="no roster"):
        CONDITION_A.roster("nonexistent")


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def test_lookup_by_key_and_label() -> None:
    assert condition_by_key("a") is CONDITION_A
    assert condition_by_key("B") is CONDITION_B
    assert condition_by_label("mixed") is CONDITION_C

    with pytest.raises(KeyError):
        condition_by_key("Z")
    with pytest.raises(KeyError):
        condition_by_label("nonexistent")
