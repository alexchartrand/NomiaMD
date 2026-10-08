"""Unit tests for CodeSectionWhereBuilder (app/lancedb/scope.py) — the SQL it renders. What
LanceDB actually does with it on a hybrid query is pinned against a real table in
test_lancedb_code_repository.py."""

from app.lancedb.scope import CodeSectionWhereBuilder


def _build(*sections: str) -> str | None:
    return CodeSectionWhereBuilder().build(sections)


def test_no_section_renders_no_clause():
    assert _build() is None
    assert CodeSectionWhereBuilder().build(None) is None


def test_one_section_renders_a_prefix_match():
    assert _build("B — Consultation") == "header_path LIKE 'B — Consultation%'"


def test_several_sections_match_any_of_them():
    assert _build("B —", "C —") == "(header_path LIKE 'B —%' OR header_path LIKE 'C —%')"


def test_quotes_and_like_wildcards_are_escaped():
    assert _build("d'un 50%_x") == "header_path LIKE 'd''un 50\\%\\_x%'"
