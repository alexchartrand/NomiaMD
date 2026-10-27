"""An encounter's latest extraction as it was stored, read back in the shape /extract
returned it (BillingExtractionResponse) — so the review UI renders a run from the inbox
the same way it renders one it just ran."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.models import BillingExtractionResponse, RunSettingOut
from app.postgresdb import Encounter, ExtractionRepository, ExtractionRun, ExtractionRunResult
from app.ramq_codes import BillingCodesResult, CodeSelector
from app.summary import ConsultationDigestBuilder, ConsultationSummarizer


class StoredExtractionLoader:
    def __init__(self, session: AsyncSession) -> None:
        self._runs = ExtractionRepository(session)

    async def latest(self, encounters: Sequence[Encounter]) -> dict[int, BillingExtractionResponse]:
        """Each encounter's newest run, keyed by encounter id; encounters never extracted
        are absent. Four queries whatever the number of encounters."""
        run_ids = await self._runs.latest_run_ids([encounter.id for encounter in encounters])
        runs = await self._runs.get_runs(list(run_ids.values()))
        billing = await self._runs.get_results(list(run_ids.values()), CodeSelector.NAME)
        summaries = await self._runs.get_results(list(run_ids.values()), ConsultationSummarizer.NAME)
        loaded = {}
        for encounter in encounters:
            run_id = run_ids.get(encounter.id)
            if run_id is None or run_id not in billing:
                continue
            loaded[encounter.id] = _response(encounter, runs[run_id], billing[run_id], summaries.get(run_id))
        return loaded

    async def latest_one(self, encounter: Encounter) -> BillingExtractionResponse | None:
        return (await self.latest([encounter])).get(encounter.id)


def _response(
    encounter: Encounter, run: ExtractionRun, billing: ExtractionRunResult, summary: ExtractionRunResult | None
) -> BillingExtractionResponse:
    return BillingExtractionResponse(
        billing=BillingCodesResult.model_validate(billing.result_json),
        extraction_run_id=run.id,
        # The encounter's own date: the source's when it sent one, else what the summary
        # found (ExtractionRecorder.save) — the one a claim from it is dated with.
        encounter_date=encounter.service_date,
        encounter_date_raw=_raw_date(summary),
        summary=ConsultationDigestBuilder().from_stored(summary.result_json) if summary else None,
        setting=RunSettingOut(
            care_setting=run.care_setting,
            shift_id=run.shift_id,
            shift_period=run.shift_period,
            day_type=run.day_type,
        ),
    )


def _raw_date(summary: ExtractionRunResult | None) -> str | None:
    if summary is None:
        return None
    return (summary.result_json.get("encounter_setting") or {}).get("date")
