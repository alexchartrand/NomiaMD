"""The billing_codes answer -> BillingCodesResult, keeping only well-formed codes that were
actually offered."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from app.ramq_codes.models import BillingCodesResult


@dataclass(frozen=True)
class SelectionDrops:
    """What the model returned before parsing dropped anything: its code count (both lists),
    the entries that weren't even code objects, and the codes never offered (invented)."""

    raw_code_count: int = 0
    malformed: int = 0
    not_offered: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedSelection:
    result: BillingCodesResult
    drops: SelectionDrops


class SelectionParser:
    def parse(self, raw: dict[str, Any], offered: Collection[str]) -> ParsedSelection:
        """The model's two lists (BillingCodesOutput) -> one list, its sure codes first,
        each marked `retained` or not; a code in both lists counts as retained. `offered` is
        the candidate numbers the prompt listed."""
        # Small local models (freeform JSON, no grammar constraint) sometimes collapse a
        # code array to bare code strings instead of the required object shape,
        # especially with a large real candidate list. Drop anything malformed rather than
        # crashing the request — and rather than fabricating an explanation for it, since
        # that field exists specifically so a physician can see the model's reasoning for
        # the suggestion; a made-up explanation would defeat that.
        codes = []
        for key, retained in (("codes", True), ("other_possible_codes", False)):
            codes += [{**c, "retained": retained} if isinstance(c, dict) else c for c in raw.get(key) or []]
        well_formed = [c for c in codes if isinstance(c, dict)]

        # Defense in depth: the "only choose from candidates" constraint is stated in the
        # prompt, and enforced here server-side.
        in_set = [c for c in well_formed if c.get("code") in offered]
        drops = SelectionDrops(
            raw_code_count=len(codes),
            malformed=len(codes) - len(well_formed),
            not_offered=tuple(str(c.get("code")) for c in well_formed if c.get("code") not in offered),
        )

        # Retained codes come first, so a code in both lists keeps its retained entry.
        unique: dict[str, dict] = {}
        for c in in_set:
            unique.setdefault(c.get("code"), c)
        result = BillingCodesResult.model_validate(
            {"codes": list(unique.values()), "notes": raw.get("notes"), "analysis": raw.get("analysis")}
        )
        self._demote_unsure_retained(result)
        self._note_drops(result, drops)
        return ParsedSelection(result=result, drops=drops)

    @staticmethod
    def _demote_unsure_retained(result: BillingCodesResult) -> None:
        """A code the model says it is sure of, but without high confidence, is only a
        possible one: over the selection benchmark (backend/benchmarks/README.md), retained
        codes rated medium or low were right 2 times in 26, high ones about 2 in 3. Retained
        codes stay first."""
        for code in result.codes:
            if code.retained and code.confidence != "high":
                code.retained = False
        result.codes.sort(key=lambda code: not code.retained)

    @staticmethod
    def _note_drops(result: BillingCodesResult, drops: SelectionDrops) -> None:
        notes: list[str] = []
        if drops.malformed:
            notes.append(
                f"{drops.malformed} candidate code(s) came back from the model in an unexpected "
                "format (missing an explanation) and were dropped rather than shown unverified."
            )
        if drops.not_offered:
            notes.append(
                f"{len(drops.not_offered)} code(s) returned by the model were not in the offered "
                "candidate list and were dropped rather than shown unverified."
            )
        if notes:
            combined = " ".join(notes)
            result.notes = f"{result.notes} {combined}".strip() if result.notes else combined
