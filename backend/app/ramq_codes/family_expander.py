"""Third retrieval step: complete each retrieved code's family. The manual's variants of one
service (same `header_path`: prise en charge / suivi, niveau A / B, a supplement and its
base visit) differ by a word or two, so the queries often surface one of them but not the
one that was billed. Picking the variant is the selection model's job (with the physician
confirming unresolved axes); retrieval's job is to put every eligible variant in front of
it.

Siblings are inserted right after their family's highest-ranked member, so they never push
a better-ranked family out of the top of the list, and only small families are expanded —
a procedure family can hold hundreds of rows. The unresolved axes are re-detected over the
expanded list, since a sibling can be bound on an axis no original candidate was."""

from app.lancedb.converter import IConverter
from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.candidate_fuser import FusedCandidate, FusedCandidates
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import UnresolvedAxisDetector
from app.ramq_codes.models import Code

__all__ = ["DEFAULT_MAX_FAMILY_SIZE", "FamilyExpander"]

# Benchmarked on the 58 labeled notes (2026-10-08): 6 found every family-only code; larger
# caps found nothing more and roughly doubled the candidate list.
DEFAULT_MAX_FAMILY_SIZE = 6


class FamilyExpander:
    def __init__(
        self,
        codes: ICodeRepository,
        converter: IConverter[CodeRow, Code],
        max_family_size: int = DEFAULT_MAX_FAMILY_SIZE,
        axis_detector: UnresolvedAxisDetector | None = None,
    ):
        """`max_family_size`: the most eligible variants a family may have to be expanded;
        0 turns expansion off."""
        self._codes = codes
        self._converter = converter
        self._max_family_size = max_family_size
        self._axis_detector = axis_detector or UnresolvedAxisDetector()

    async def expand(
        self, fused: FusedCandidates, eligibility: CodeEligibilityFilter, context: BillingContext
    ) -> FusedCandidates:
        if self._max_family_size <= 0 or not fused.ranked:
            return fused

        families = await self._families([c.code.header_path for c in fused.ranked], eligibility)
        present = {c.code.number for c in fused.ranked}
        ranked: list[FusedCandidate] = []
        for candidate in fused.ranked:
            ranked.append(candidate)
            for sibling in families.pop(candidate.code.header_path, []):
                if sibling.number not in present:
                    present.add(sibling.number)
                    ranked.append(FusedCandidate(code=sibling, rrf_score=0.0, expanded_from=candidate.code.number))

        codes = [c.code for c in ranked]
        return FusedCandidates(ranked=ranked, unresolved_axes=self._axis_detector.detect(codes, context))

    async def _families(self, header_paths: list[str], eligibility: CodeEligibilityFilter) -> dict[str, list[Code]]:
        """Each expandable header_path's eligible variants, in code-number order."""
        unique = sorted({path for path in header_paths if path})
        families: dict[str, list[Code]] = {}
        for row in await self._codes.list_by_header_paths(unique, eligibility):
            families.setdefault(row.header_path, []).append(self._converter.convert(row))
        return {
            path: sorted(members, key=lambda code: code.number)
            for path, members in families.items()
            if len(members) <= self._max_family_size
        }
