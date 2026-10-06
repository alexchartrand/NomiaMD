"""CodeRow (a row of the current codes table) -> this module's API shapes."""

from app.code_catalog.models import CodeDetail, CodeEligibilityOut, CodeHit
from app.lancedb.models import CodeRow
from app.ramq_codes import CodeFeeOut


class CodeHitMapper:
    @staticmethod
    def to_hit(row: CodeRow, needs_confirmation: list[str]) -> CodeHit:
        return CodeHit(
            number=row.number,
            description=row.description,
            header_path=row.header_path,
            fees=[CodeFeeOut.model_validate(fee.model_dump()) for fee in row.fees],
            needs_confirmation=needs_confirmation,
        )

    @classmethod
    def to_detail(cls, row: CodeRow) -> CodeDetail:
        return CodeDetail(
            **cls.to_hit(row, []).model_dump(),
            when_to_use=row.when_to_use,
            rules=row.rules,
            eligibility=CodeEligibilityOut(
                min_age=row.min_age,
                max_age=row.max_age,
                min_panel_size=row.min_panel_size,
                max_panel_size=row.max_panel_size,
                requires_registered=row.requires_registered,
                requires_vulnerable=row.requires_vulnerable,
            ),
        )
