"""Business logic for turning a physician-reviewed extraction into a claim — the codes the
run suggested plus any the physician added from the code search. Constructor-injected
(ClaimRepository, PatientRepository, ExtractionRepository, EncounterRepository, plus the
ClaimDuplicateGuard, ClaimLineBuilder, ClaimContextSnapshotter and ClaimCodeResolver it
composes) — wired at the module boundary by factory.py, no FastAPI/HTTP concerns here. A claim
billed without an encounter is manual.py's ManualClaimService."""

from datetime import date

from app.claims.candidates import ExtractionCandidates
from app.claims.code_resolver import ClaimCodeResolver
from app.claims.context import ClaimContextSnapshotter
from app.claims.duplicates import EXTRACTION_ALREADY_CLAIMED, ClaimDuplicateGuard
from app.claims.errors import (
    ClaimEncounterMismatchError,
    ClaimNotFoundError,
    ClaimOnBillError,
    DuplicateClaimError,
    DuplicateEncounterClaimError,
    ExtractionRunNotFoundError,
    PatientNotFoundError,
)
from app.claims.lines import ClaimLineBuilder
from app.claims.mapper import ClaimMapper
from app.claims.models import ClaimOut, SelectedCode
from app.claims.status import ClaimLifecycle, ClaimStatus
from app.postgresdb import (
    ClaimInput,
    ClaimRepository,
    Encounter,
    EncounterRepository,
    ExtractionAlreadyClaimedError,
    ExtractionRepository,
    ExtractionRun,
    PatientRepository,
    User,
)

BILLING_TASK = "billing_codes"


class ClaimService:
    def __init__(
        self,
        claim_repository: ClaimRepository,
        patient_repository: PatientRepository,
        extraction_repository: ExtractionRepository,
        encounter_repository: EncounterRepository,
        duplicate_guard: ClaimDuplicateGuard,
        line_builder: ClaimLineBuilder,
        context_snapshotter: ClaimContextSnapshotter,
        code_resolver: ClaimCodeResolver,
    ):
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._extraction_repository = extraction_repository
        self._encounter_repository = encounter_repository
        self._duplicate_guard = duplicate_guard
        self._line_builder = line_builder
        self._context_snapshotter = context_snapshotter
        self._code_resolver = code_resolver

    async def create(
        self,
        *,
        physician: User,
        extraction_run_id: int,
        service_date: date,
        selected_codes: list[SelectedCode],
        confirm_duplicate: bool,
    ) -> ClaimOut:
        selected = ClaimLineBuilder.dedupe(selected_codes)
        run = await self._owned_run(extraction_run_id, physician.id)

        # The patient is the one the run's codes were eligibility-filtered for — never a
        # different one from the request. Any physician may claim any known patient
        # (Patient is a global identity), but not one soft-deleted since the extraction.
        patient = await self._patient_repository.get(run.patient_id)
        if patient is None:
            raise PatientNotFoundError()

        # The note the run was extracted from: its source and version are snapshotted onto
        # the claim, so they survive the encounter's retention purge.
        encounter = await self._run_encounter(run, physician.id)
        if encounter.duplicate_of_id is not None:
            raise DuplicateEncounterClaimError()

        await self._duplicate_guard.ensure_run_unclaimed(run.id)
        context = await self._context_snapshotter.snapshot(
            physician=physician, patient_id=patient.id, service_date=service_date
        )
        # A code the run offered is billed as suggested; any other the physician added from
        # the code search, eligibility-checked against this same context.
        candidates = await self._code_resolver.resolve(
            [s.code for s in selected], await self._run_candidates(run.id), context.eligibility
        )
        if not confirm_duplicate:
            await self._duplicate_guard.ensure_first_on_date(physician.id, patient.id, service_date)

        try:
            created = await self._claim_repository.create(
                ClaimInput(
                    physician_id=physician.id,
                    patient_id=patient.id,
                    service_date=service_date,
                    source_system=encounter.source_system,
                    source_note_hash=encounter.content_hash,
                    external_note_id=encounter.external_note_id,
                    extraction_run_id=run.id,
                    context=context.record,
                    codes=self._line_builder.build(selected, candidates),
                )
            )
        except ExtractionAlreadyClaimedError as exc:
            raise DuplicateClaimError(EXTRACTION_ALREADY_CLAIMED) from exc

        return ClaimMapper.to_out(created.claim, patient.full_name, created.codes)

    async def replace(
        self,
        *,
        claim_id: int,
        physician: User,
        extraction_run_id: int,
        service_date: date,
        selected_codes: list[SelectedCode],
        confirm_duplicate: bool,
    ) -> ClaimOut:
        """The physician changed their review of a draft: void it and save the new selection
        in its place, from the same encounter's latest run (or any of its runs). Nothing is
        edited in place, so the voided claim keeps what was first saved. Both happen in the
        request's session: if the new claim is refused, the old one is left live."""
        claim = await self._claim_repository.get_for_physician(claim_id, physician.id)
        if claim is None:
            raise ClaimNotFoundError()
        if not ClaimLifecycle.can_be_voided(claim):
            raise ClaimOnBillError()
        new_run = await self._owned_run(extraction_run_id, physician.id)
        old_run = (
            await self._extraction_repository.get_run_for_user(claim.extraction_run_id, physician.id)
            if claim.extraction_run_id is not None
            else None
        )
        if old_run is None or old_run.encounter_id != new_run.encounter_id:
            raise ClaimEncounterMismatchError()

        await self._claim_repository.void(claim)
        return await self.create(
            physician=physician,
            extraction_run_id=extraction_run_id,
            service_date=service_date,
            selected_codes=selected_codes,
            confirm_duplicate=confirm_duplicate,
        )

    async def _owned_run(self, run_id: int, physician_id: int) -> ExtractionRun:
        run = await self._extraction_repository.get_run_for_user(run_id, physician_id)
        if run is None:
            raise ExtractionRunNotFoundError()
        return run

    async def _run_encounter(self, run: ExtractionRun, physician_id: int) -> Encounter:
        encounter = await self._encounter_repository.get_for_user(run.encounter_id, physician_id)
        if encounter is None:
            raise ExtractionRunNotFoundError()
        return encounter

    async def _run_candidates(self, run_id: int) -> ExtractionCandidates:
        result = await self._extraction_repository.get_result(run_id, BILLING_TASK)
        if result is None:
            raise ExtractionRunNotFoundError()
        return ExtractionCandidates.from_result_json(result.result_json)

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        patient_id: int | None,
        date_from: date | None,
        date_to: date | None,
        status: ClaimStatus | None,
        limit: int,
        offset: int,
    ) -> list[ClaimOut]:
        details = await self._claim_repository.list_for_physician(
            physician_id,
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            billed=ClaimLifecycle.is_billed(status) if status is not None else None,
            limit=limit,
            offset=offset,
        )
        return [ClaimMapper.from_detail(d) for d in details]

    async def get(self, claim_id: int, physician_id: int) -> ClaimOut | None:
        details = await self._claim_repository.list_by_ids(physician_id, [claim_id])
        return ClaimMapper.from_detail(details[0]) if details else None

    async def void(self, claim_id: int, physician_id: int) -> bool:
        """Voids a draft (never a hard delete — see the Claim model). Once a claim is on a
        bill, it can only be freed by voiding that bill first, or a bill's total would
        silently shrink behind the physician's back."""
        claim = await self._claim_repository.get_for_physician(claim_id, physician_id)
        if claim is None:
            return False
        if not ClaimLifecycle.can_be_voided(claim):
            raise ClaimOnBillError()
        await self._claim_repository.void(claim)
        return True
