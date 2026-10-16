from app.lancedb.repository import ICodeRepository
from app.ramq_codes.models import BillingCodesResult, CodeFeeOut


class FeeResolver:
    """Attaches each selected code's real fee list — the model never picks a fee (see
    app/ramq_codes/prompt.py's SYSTEM_PROMPT and ExtractedCode.fees' server_only marker); the
    physician picks among these in the review UI when there's more than one."""

    def __init__(self, codes: ICodeRepository):
        self._codes = codes

    async def attach(self, result: BillingCodesResult) -> None:
        """In place. A by-key lookup, same convention as ramq_chatbot's ReferenceExpander: a
        code with no matching row is left with an empty fee list rather than surfaced as
        missing data."""
        if not result.codes:
            return  # list_by_numbers([]) would build a malformed "IN ()" query

        rows = await self._codes.list_by_numbers([c.code for c in result.codes])
        fees_by_code = {row.number: row.fees for row in rows}
        for code in result.codes:
            code.fees = [CodeFeeOut.model_validate(f.model_dump()) for f in fees_by_code.get(code.code, [])]
