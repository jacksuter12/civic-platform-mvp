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
    RECALL_MODES,
    RECALL_NONE,
    RECALL_OWN,
    TIER_FACILITATOR,
    Bot,
    Condition,
    condition_by_key,
    condition_by_label,
    find_leak_terms,
)

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
        roster=(Bot("a", "A. Person"),),
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
        pytest.param(lambda c: [b.display_name for b in c.roster], id="display_name"),
        pytest.param(lambda c: [c.email(b) for b in c.roster], id="email"),
        pytest.param(lambda c: [c.supabase_uid(b) for b in c.roster], id="uid"),
        pytest.param(lambda c: [c.env_var(b) for b in c.roster], id="env_var"),
    ],
)
def test_no_value_is_shared_across_conditions(extract) -> None:
    values = [value for condition in CONDITIONS for value in extract(condition)]
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    assert duplicates == []


def test_every_condition_has_exactly_one_facilitator() -> None:
    for condition in CONDITIONS:
        facilitator = condition.facilitator()
        assert facilitator.tier == TIER_FACILITATOR
        others = [b for b in condition.roster if b is not facilitator]
        assert all(b.tier == "registered" for b in others)


def test_every_condition_has_a_full_roster() -> None:
    for condition in CONDITIONS:
        assert len(condition.roster) >= 4, condition.key


# ---------------------------------------------------------------------------
# Derived identity — the seed's idempotency depends on these being stable
# ---------------------------------------------------------------------------


def test_derived_identity_matches_the_documented_shape() -> None:
    claude = CONDITION_A.roster[0]
    assert claude.bot_slug == "claude-panel"
    assert CONDITION_A.supabase_uid(claude) == "llm-panel-a-claude-panel"
    assert CONDITION_A.email(claude) == "a-claude-panel@llm-panel.example"
    assert CONDITION_A.env_var(claude) == "A_CLAUDE_PANEL_JWT"

    alvarez = CONDITION_B.roster[0]
    assert CONDITION_B.env_var(alvarez) == "B_ALVAREZ_JWT"


def test_bot_emails_avoid_special_use_domains() -> None:
    """
    `.local` and `.invalid` are rejected by the platform's EmailStr validation
    at POST /auth/register. `.example` is reserved for exactly this (RFC 2606).
    """
    for condition in CONDITIONS:
        for bot in condition.roster:
            assert condition.email(bot).endswith("@llm-panel.example")


def test_display_names_fit_the_platform_constraints() -> None:
    """display_name is 2-60 chars and must not look like a full name (>3 words)."""
    for condition in CONDITIONS:
        for bot in condition.roster:
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
    assert Bot("x", "X. Person").recall == RECALL_NONE
    for condition in (CONDITION_B, CONDITION_C):
        assert all(b.recall == RECALL_NONE for b in condition.roster), condition.key


def test_condition_a_carries_the_mixed_pilot_assignment() -> None:
    """One participant with recall, the rest without — used only by --recall mixed."""
    by_recall = Counter(b.recall for b in CONDITION_A.roster)
    assert by_recall[RECALL_OWN] == 1
    assert by_recall[RECALL_NONE] == 3
    assert CONDITION_A.roster[0].display_name == "Claude Panel"
    assert CONDITION_A.roster[0].recall == RECALL_OWN


@pytest.mark.parametrize("mode", RECALL_MODES)
def test_with_recall_forces_every_participant_to_one_mode(mode: str) -> None:
    """
    The uniform form is what an actual comparison uses — same thread prompt,
    two runs, recall the only difference.
    """
    forced = CONDITION_A.with_recall(mode)
    assert all(b.recall == mode for b in forced.roster)
    # Identity is untouched: same names, same slugs, same tiers.
    assert [b.display_name for b in forced.roster] == [
        b.display_name for b in CONDITION_A.roster
    ]
    assert [b.tier for b in forced.roster] == [b.tier for b in CONDITION_A.roster]
    assert forced.slug == CONDITION_A.slug


def test_with_recall_mixed_leaves_the_roster_alone() -> None:
    assert CONDITION_A.with_recall("mixed") is CONDITION_A


def test_with_recall_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Unknown recall mode"):
        CONDITION_A.with_recall("telepathy")


def test_with_recall_does_not_mutate_the_committed_condition() -> None:
    """Conditions are frozen; a forced copy must not leak back into the table."""
    CONDITION_A.with_recall(RECALL_OWN)
    assert Counter(b.recall for b in CONDITION_A.roster)[RECALL_OWN] == 1


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
