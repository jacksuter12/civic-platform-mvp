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
