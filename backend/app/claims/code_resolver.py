"""Which source each code the physician selected is snapshotted from: the extraction run's
stored result when the run offered it, the current codes table (eligibility-checked)
otherwise. Without a run — a claim billed without an encounter — every code is a hand-picked
one."""

from app.claims.candidates import ExtractionCandidates, StoredCandidate
from app.claims.catalog import CatalogCodes
from app.lancedb import CodeEligibilityFilter


class ClaimCodeResolver:
    def __init__(self, catalog: CatalogCodes):
        self._catalog = catalog

    async def resolve(
        self,
        codes: list[str],
        run_candidates: ExtractionCandidates | None,
        eligibility: CodeEligibilityFilter,
    ) -> list[StoredCandidate]:
        """One candidate per code, in the order given."""
        suggested = {
            code: candidate
            for code in codes
            if run_candidates is not None and (candidate := run_candidates.get(code)) is not None
        }
        added = [code for code in codes if code not in suggested]
        from_catalog = {c.code: c for c in await self._catalog.require(added, eligibility)}
        return [suggested.get(code) or from_catalog[code] for code in codes]
