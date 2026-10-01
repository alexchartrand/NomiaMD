"""The patient picker's search rules (PatientSearchSelect.tsx): how much the physician must
type before anything is searched, how many matches come back, and whether the query is a
NAM. The repository only runs the resulting query."""

from app.patients import nam
from app.postgresdb import Patient, PatientRepository

# Two characters, so a stray keystroke doesn't fan out into a live full-table scan.
_MIN_QUERY_LENGTH = 2
_RESULT_LIMIT = 20


class PatientSearch:
    def __init__(self, patients: PatientRepository) -> None:
        self._patients = patients

    async def search(self, query: str) -> list[Patient]:
        """Matches a substring of the full name, or — when the query is a well-formed NAM in
        any spacing/case — that exact NAM (stored canonical, see PatientBase)."""
        trimmed = query.strip()
        if len(trimmed) < _MIN_QUERY_LENGTH:
            return []
        return await self._patients.search(
            name_fragment=trimmed, ramq_number=nam.normalize(trimmed), limit=_RESULT_LIMIT
        )
