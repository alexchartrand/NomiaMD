"""Turns the facts known about an encounter into a LanceDB prefilter over the codes table's
typed eligibility columns (min_age … requires_vulnerable — see models.py's CodeRow).

Every clause is null-safe: a null bound means "no restriction on this axis" in
ramq-ingestion's convention, so a code with no bound on an axis always survives it. Only
known facts produce a clause — an unknown fact filters nothing, and the variants it leaves
in place are flagged for the physician to confirm (see app/ramq_codes/eligibility.py)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeEligibilityFilter:
    """The facts to filter on. Each field is None when unknown. Ages are whole years, to
    compare against the columns' inclusive whole-year bounds."""

    age: int | None = None
    panel_size: int | None = None
    is_registered: bool | None = None
    is_vulnerable: bool | None = None


class CodeEligibilityWhereBuilder:
    """Renders a CodeEligibilityFilter as a LanceDB SQL predicate."""

    def build(self, eligibility: CodeEligibilityFilter) -> str | None:
        clauses: list[str] = []
        if eligibility.age is not None:
            clauses += self._range("age", eligibility.age)
        if eligibility.panel_size is not None:
            clauses += self._range("panel_size", eligibility.panel_size)
        if eligibility.is_registered is not None:
            clauses.append(self._flag("requires_registered", eligibility.is_registered))
        if eligibility.is_vulnerable is not None:
            clauses.append(self._flag("requires_vulnerable", eligibility.is_vulnerable))

        if not clauses:
            return None
        return " AND ".join(clauses)

    @staticmethod
    def _range(axis: str, value: int) -> list[str]:
        # int() rather than trusting the dataclass annotation: this value is interpolated
        # into SQL.
        value = int(value)
        return [
            f"(min_{axis} IS NULL OR min_{axis} <= {value})",
            f"(max_{axis} IS NULL OR max_{axis} >= {value})",
        ]

    @staticmethod
    def _flag(column: str, value: bool) -> str:
        return f"({column} IS NULL OR {column} = {'true' if value else 'false'})"
