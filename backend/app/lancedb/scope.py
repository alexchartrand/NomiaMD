"""Restricts a code search to some sections of the manual, by `header_path` prefix — e.g.
only "B — Consultation, examen et visite" for a visit query, whose code is always there.

Separate from eligibility.py on purpose: eligibility is about the encounter's facts (a
variant that contradicts one is never billable), scope is about which part of the manual a
given query is meant to search. Prefixes are code constants of the callers, never request
input; they're still quote-escaped, and LIKE wildcards in them are escaped too."""


class CodeSectionWhereBuilder:
    """Renders a tuple of `header_path` prefixes as a LanceDB SQL predicate: a row matches
    when its header_path starts with any one of them."""

    def build(self, sections: tuple[str, ...] | None) -> str | None:
        if not sections:
            return None
        clauses = [f"header_path LIKE '{self._escape(prefix)}%'" for prefix in sections]
        return clauses[0] if len(clauses) == 1 else "(" + " OR ".join(clauses) + ")"

    @staticmethod
    def _escape(prefix: str) -> str:
        # SQL quote first, then LIKE's own wildcards (DataFusion's default escape is '\').
        return prefix.replace("'", "''").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
