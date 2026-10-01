"""Unit tests for CodeEligibilityWhereBuilder (app/lancedb/eligibility.py) — the SQL it
renders. What LanceDB actually does with it on a hybrid query is pinned against a real
table in test_lancedb_code_repository.py."""

from app.lancedb.eligibility import CodeEligibilityFilter, CodeEligibilityWhereBuilder


def _build(**facts) -> str | None:
    return CodeEligibilityWhereBuilder().build(CodeEligibilityFilter(**facts))


def test_no_known_fact_renders_no_clause():
    assert _build() is None


def test_age_renders_a_null_safe_inclusive_range():
    assert _build(age=45) == "(min_age IS NULL OR min_age <= 45) AND (max_age IS NULL OR max_age >= 45)"


def test_panel_size_renders_a_null_safe_inclusive_range():
    assert _build(panel_size=500) == (
        "(min_panel_size IS NULL OR min_panel_size <= 500) AND (max_panel_size IS NULL OR max_panel_size >= 500)"
    )


def test_flags_render_null_safe_equality():
    assert _build(is_registered=True) == "(requires_registered IS NULL OR requires_registered = true)"
    assert _build(is_vulnerable=False) == "(requires_vulnerable IS NULL OR requires_vulnerable = false)"


def test_only_known_facts_are_rendered():
    where = _build(age=45, is_vulnerable=True)

    assert "age" in where
    assert "requires_vulnerable" in where
    assert "panel_size" not in where
    assert "requires_registered" not in where
