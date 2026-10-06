"""Code search and lookup over the current RAMQ codes table. With a patient, the search only
offers codes that patient may be billed (the same deterministic eligibility filter an
extraction's retrieval uses — an assumed panel size never filters) and says what's left to
confirm; without one (the reference page), every code is offered."""

from datetime import date

from app.code_catalog.confirmation import CodeConfirmationNotes
from app.code_catalog.frequent import FrequentCodes
from app.code_catalog.mapper import CodeHitMapper
from app.code_catalog.models import CodeDetail, CodeHit
from app.code_catalog.query import CodeQueryKind, CodeQueryParser
from app.lancedb import CodeEligibilityFilter, CodeRowLookupError, ICodeCatalogRepository
from app.lancedb.models import CodeRow
from app.postgresdb import User
from app.ramq_codes import BillingContext, BillingContextBuilder, EligibilityFilterFactory


class CodeNotFoundError(Exception):
    pass


class CodeCatalogService:
    def __init__(
        self,
        codes: ICodeCatalogRepository,
        frequent: FrequentCodes,
        context_builder: BillingContextBuilder,
        parser: CodeQueryParser | None = None,
        filter_factory: EligibilityFilterFactory | None = None,
        confirmation: CodeConfirmationNotes | None = None,
    ):
        self._codes = codes
        self._frequent = frequent
        self._context_builder = context_builder
        self._parser = parser or CodeQueryParser()
        self._filter_factory = filter_factory or EligibilityFilterFactory()
        self._confirmation = confirmation or CodeConfirmationNotes()

    async def search(
        self,
        *,
        physician: User,
        q: str | None,
        patient_id: int | None,
        service_date: date | None,
        limit: int,
    ) -> list[CodeHit]:
        context = (
            await self._context_builder.build(user=physician, patient_id=patient_id, encounter_date=service_date)
            if patient_id is not None
            else None
        )
        eligibility = self._filter_factory.from_context(context) if context is not None else None
        rows = await self._rows(physician, q, limit, eligibility)
        return [CodeHitMapper.to_hit(row, self._confirmation.for_code(row, context)) for row in rows]

    async def get(self, number: str) -> CodeDetail:
        try:
            return CodeHitMapper.to_detail(await self._codes.get_by_number(number))
        except CodeRowLookupError as exc:
            raise CodeNotFoundError(number) from exc

    async def _rows(
        self, physician: User, q: str | None, limit: int, eligibility: CodeEligibilityFilter | None
    ) -> list[CodeRow]:
        query = self._parser.parse(q)
        if query.kind is CodeQueryKind.EMPTY:
            return await self._frequent.for_physician(physician.id, limit, eligibility)
        if query.kind is CodeQueryKind.NUMBER_PREFIX:
            return await self._codes.list_by_number_prefix(query.value, limit, eligibility)
        return [row for row, _score in await self._codes.keyword_search(query.value, limit, eligibility)]
