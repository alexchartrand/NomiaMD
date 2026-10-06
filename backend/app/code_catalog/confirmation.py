"""What the physician must still confirm before billing a hand-picked code: the eligibility
axes it's bound on that the patient's billing context couldn't resolve. Same rule as an
extraction's candidates (UnresolvedAxisDetector), applied to one code at a time, in the same
French wording the billing_codes model is given."""

from app.lancedb.models import CodeRow
from app.ramq_codes import AXIS_LABELS_FR, BillingContext, CodesRowConverter, UnresolvedAxisDetector


class CodeConfirmationNotes:
    def __init__(
        self, converter: CodesRowConverter | None = None, detector: UnresolvedAxisDetector | None = None
    ):
        self._converter = converter or CodesRowConverter()
        self._detector = detector or UnresolvedAxisDetector()

    def for_code(self, row: CodeRow, context: BillingContext | None) -> list[str]:
        if context is None:
            return []
        axes = self._detector.detect([self._converter.convert(row)], context)
        return [AXIS_LABELS_FR[axis] for axis in axes if axis in AXIS_LABELS_FR]
