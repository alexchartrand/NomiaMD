"""The physician's selection -> the claim_codes rows a claim is saved with, shared by the
encounter and the no-encounter claim paths: one line per code, snapshotted from its resolved
candidate (never the request body) with the fee the physician picked."""

from app.claims.candidates import StoredCandidate
from app.claims.errors import EmptySelectionError
from app.claims.fees import FeeSnapshotter
from app.claims.models import SelectedCode
from app.postgresdb import ClaimCodeInput


class ClaimLineBuilder:
    def __init__(self, fee_snapshotter: FeeSnapshotter | None = None):
        self._fee_snapshotter = fee_snapshotter or FeeSnapshotter()

    @staticmethod
    def dedupe(selected_codes: list[SelectedCode]) -> list[SelectedCode]:
        """First choice per code wins; an empty selection is refused."""
        by_code: dict[str, SelectedCode] = {}
        for selected in selected_codes:
            by_code.setdefault(selected.code, selected)
        if not by_code:
            raise EmptySelectionError()
        return list(by_code.values())

    def build(self, selected: list[SelectedCode], candidates: list[StoredCandidate]) -> list[ClaimCodeInput]:
        """`candidates` holds one candidate per selected code, in the same order."""
        return [self._line(candidate, choice) for choice, candidate in zip(selected, candidates, strict=True)]

    def _line(self, candidate: StoredCandidate, choice: SelectedCode) -> ClaimCodeInput:
        fee = self._fee_snapshotter.snapshot(candidate, choice.fee_index, choice.lieu)
        return ClaimCodeInput(
            code=candidate.code,
            description=candidate.description,
            confidence=candidate.confidence,
            explanation=candidate.explanation,
            fee_amount=fee.amount,
            fee_unit=fee.unit,
            fee_units=fee.units,
            fee_role=fee.role,
            fee_context=fee.context,
            fee_lieux=fee.lieux,
            majoration=fee.majoration,
            manual_rev=candidate.manual_rev,
            origin=candidate.origin.value,
        )
