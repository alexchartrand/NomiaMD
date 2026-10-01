"""An encounter's latest extraction as it was stored, read back in the shape /extract
returned it (BillingExtractionResponse) — so the review UI renders a run from the inbox
the same way it renders one it just ran."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.models import BillingExtractionResponse, ExtractionResult
from app.postgresdb import Encounter, ExtractionRepository, ExtractionRunResult
from app.ramq_codes import BillingCodesResult

_SUMMARY_TASK = "consultation_summary"
_BILLING_TASK = "billing_codes"


class StoredExtractionLoader:
    def __init__(self, session: AsyncSession) -> None:
        self._runs = ExtractionRepository(session)

    async def latest(self, encounters: Sequence[Encounter]) -> dict[int, BillingExtractionResponse]:
        """Each encounter's newest run, keyed by encounter id; encounters never extracted
        are absent. Three queries whatever the number of encounters."""
        run_ids = await self._runs.latest_run_ids([encounter.id for encounter in encounters])
        billing = await self._runs.get_results(list(run_ids.values()), _BILLING_TASK)
        summaries = await self._runs.get_results(list(run_ids.values()), _SUMMARY_TASK)
        loaded = {}
        for encounter in encounters:
            run_id = run_ids.get(encounter.id)
            if run_id is None or run_id not in billing:
                continue
            loaded[encounter.id] = _response(encounter, run_id, billing[run_id], summaries.get(run_id))
        return loaded

    async def latest_one(self, encounter: Encounter) -> BillingExtractionResponse | None:
        return (await self.latest([encounter])).get(encounter.id)


def _response(
    encounter: Encounter, run_id: int, billing: ExtractionRunResult, summary: ExtractionRunResult | None
) -> BillingExtractionResponse:
    return BillingExtractionResponse(
        billing=ExtractionResult[BillingCodesResult](
            task=billing.task,
            result=BillingCodesResult.model_validate(billing.result_json),
            model=billing.model,
            created_at=billing.created_at,
        ),
        extraction_run_id=run_id,
        # The encounter's own date: the source's when it sent one, else what the summary
        # found (ExtractionRecorder.save) — the one a claim from it is dated with.
        encounter_date=encounter.service_date,
        encounter_date_raw=_raw_date(summary),
    )


def _raw_date(summary: ExtractionRunResult | None) -> str | None:
    if summary is None:
        return None
    return (summary.result_json.get("encounter_setting") or {}).get("date")
