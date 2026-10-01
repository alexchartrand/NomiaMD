"""CodeRow (a validated row of the current `codes_<rev>` LanceDB table) -> this package's own
Code — the one place the table's flat columns become the domain shape retrieval and the
billing_codes task work in."""

from app.lancedb.converter import IConverter
from app.lancedb.models import CodeRow
from app.ramq_codes.models import Code, CodeEligibility, CodeFee


class CodesRowConverter(IConverter[CodeRow, Code]):
    def convert(self, data: CodeRow) -> Code:
        return Code(
            number=data.number,
            description=data.description,
            header_path=data.header_path,
            when_to_use=tuple(data.when_to_use),
            rules=tuple(data.rules),
            fees=tuple(
                CodeFee(
                    amount=fee.amount,
                    amount_text=fee.amount_text,
                    context=fee.context,
                    majoration=fee.majoration,
                    lieux=tuple(fee.lieux),
                    role=fee.role,
                    unit=fee.unit,
                )
                for fee in data.fees
            ),
            eligibility=CodeEligibility(
                min_age=data.min_age,
                max_age=data.max_age,
                min_panel_size=data.min_panel_size,
                max_panel_size=data.max_panel_size,
                requires_registered=data.requires_registered,
                requires_vulnerable=data.requires_vulnerable,
            ),
        )
