"""A claim billed without an encounter — no note, no extraction run: the physician names the
patient and picks every code from the code search. The codes are eligibility-checked against
that patient on the service date and snapshotted from the current codes table (catalog.py),
like a code added by hand to an encounter's claim. No same-day duplicate guard: billing by hand
is already deliberate."""

from datetime import date

from app.claims.catalog import CatalogCodes
from app.claims.context import ClaimContextSnapshotter
from app.claims.errors import ClaimEncounterMismatchError, ClaimNotFoundError, ClaimOnBillError, PatientNotFoundError
from app.claims.lines import ClaimLineBuilder
from app.claims.mapper import ClaimMapper
from app.claims.models import ClaimOut, SelectedCode
from app.claims.origin import MANUAL_SOURCE_SYSTEM
from app.claims.status import ClaimLifecycle
from app.postgresdb import ClaimInput, ClaimRepository, PatientRepository, User


class ManualClaimService:
    def __init__(
        self,
        claim_repository: ClaimRepository,
        patient_repository: PatientRepository,
        catalog: CatalogCodes,
        line_builder: ClaimLineBuilder,
        context_snapshotter: ClaimContextSnapshotter,
    ):
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._catalog = catalog
        self._line_builder = line_builder
        self._context_snapshotter = context_snapshotter

    async def create(
        self, *, physician: User, patient_id: int, service_date: date, selected_codes: list[SelectedCode]
    ) -> ClaimOut:
        selected = ClaimLineBuilder.dedupe(selected_codes)
        # Any physician may bill any known patient (Patient is a global identity), but not a
        # soft-deleted one.
        patient = await self._patient_repository.get(patient_id)
        if patient is None:
            raise PatientNotFoundError()

        context = await self._context_snapshotter.snapshot(
            physician=physician, patient_id=patient.id, service_date=service_date
        )
        candidates = await self._catalog.require([s.code for s in selected], context.eligibility)
        created = await self._claim_repository.create(
            ClaimInput(
                physician_id=physician.id,
                patient_id=patient.id,
                service_date=service_date,
                source_system=MANUAL_SOURCE_SYSTEM,
                source_note_hash=None,
                external_note_id=None,
                extraction_run_id=None,
                context=context.record,
                codes=self._line_builder.build(selected, candidates),
            )
        )
        return ClaimMapper.to_out(created.claim, patient.full_name, created.codes)

    async def replace(
        self,
        *,
        claim_id: int,
        physician: User,
        patient_id: int,
        service_date: date,
        selected_codes: list[SelectedCode],
    ) -> ClaimOut:
        """Same void-and-recreate as ClaimService.replace, so the voided claim keeps what was
        first saved — and if the new claim is refused, the old one is left live. Only a claim
        billed without an encounter can be replaced this way: an encounter's claim stays tied
        to its note."""
        claim = await self._claim_repository.get_for_physician(claim_id, physician.id)
        if claim is None:
            raise ClaimNotFoundError()
        if not ClaimLifecycle.can_be_voided(claim):
            raise ClaimOnBillError()
        if claim.source_system != MANUAL_SOURCE_SYSTEM:
            raise ClaimEncounterMismatchError()

        await self._claim_repository.void(claim)
        return await self.create(
            physician=physician, patient_id=patient_id, service_date=service_date, selected_codes=selected_codes
        )
