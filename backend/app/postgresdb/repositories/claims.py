"""`claims` and their `claim_codes` lines."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Claim, ClaimCode, ExtractionRun, Patient
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ClaimCodeInput:
    code: str
    description: str
    confidence: str | None
    explanation: str
    fee_amount: Decimal | None
    fee_unit: str | None
    fee_units: Decimal | None
    fee_role: int | None
    fee_context: str | None
    fee_lieux: list[str] | None
    majoration: str | None
    manual_rev: str | None
    origin: str = "suggested"


@dataclass
class ClaimContextInput:
    """The billing context snapshot — see Claim's docstring."""

    is_registered: bool | None
    is_vulnerable: bool | None
    patient_age_years: int | None
    panel_size: int | None


@dataclass
class ClaimInput:
    physician_id: int
    patient_id: int
    service_date: date
    source_system: str | None
    source_note_hash: str | None
    external_note_id: str | None
    extraction_run_id: int | None
    context: ClaimContextInput
    codes: Sequence[ClaimCodeInput]


class ExtractionAlreadyClaimedError(Exception):
    """The claim's extraction run is already on another live claim — the partial unique
    index on extraction_run_id is the backstop for two saves of one run racing past
    ClaimService's pre-check (app/claims/duplicates.py). The session can only be rolled back
    afterwards, which its owner does as this propagates (see session.py)."""


class ClaimAlreadyBilledError(Exception):
    """A requested claim was attached to another bill (or voided) after the caller checked
    it — attach_to_bill's conditional UPDATE is the backstop for two bills racing over the
    same claim."""


def _violates_extraction_unique(exc: IntegrityError) -> bool:
    # No portable error code across drivers: SQLite says "UNIQUE constraint failed:
    # claims.extraction_run_id", Postgres "duplicate key value violates unique constraint
    # "ix_claims_extraction_run_active"". An FK violation (e.g. an unknown physician_id)
    # mentions neither "unique constraint" and must stay an IntegrityError rather than pass
    # for a duplicate claim.
    message = str(exc.orig).lower()
    return "unique constraint" in message and "extraction_run" in message


@dataclass
class ClaimWithCodes:
    claim: Claim
    codes: list[ClaimCode]


@dataclass
class ClaimDetail:
    claim: Claim
    patient_full_name: str
    codes: list[ClaimCode]
    # The encounter its extraction run belongs to: None for a claim billed without one, or
    # once the retention purge has deleted the run.
    encounter_id: int | None = None


class ClaimRepository(SessionRepository):
    """No relationship() — manual second queries, matching the existing house style. Voided
    claims are invisible to every read here; nothing is ever hard-deleted."""

    async def create(self, data: ClaimInput) -> ClaimWithCodes:
        claim = Claim(
            physician_id=data.physician_id,
            patient_id=data.patient_id,
            service_date=data.service_date,
            source_system=data.source_system,
            source_note_hash=data.source_note_hash,
            external_note_id=data.external_note_id,
            extraction_run_id=data.extraction_run_id,
            is_registered=data.context.is_registered,
            is_vulnerable=data.context.is_vulnerable,
            patient_age_years=data.context.patient_age_years,
            panel_size=data.context.panel_size,
        )
        self._session.add(claim)
        try:
            await self._session.flush()  # populate claim.id for the code rows' FK
        except IntegrityError as exc:
            if _violates_extraction_unique(exc):
                raise ExtractionAlreadyClaimedError() from exc
            raise
        code_rows = [
            ClaimCode(
                claim_id=claim.id,
                code=c.code,
                description=c.description,
                origin=c.origin,
                confidence=c.confidence,
                explanation=c.explanation,
                fee_amount=c.fee_amount,
                fee_unit=c.fee_unit,
                fee_units=c.fee_units,
                fee_role=c.fee_role,
                fee_context=c.fee_context,
                fee_lieux=c.fee_lieux,
                majoration=c.majoration,
                manual_rev=c.manual_rev,
            )
            for c in data.codes
        ]
        self._session.add_all(code_rows)
        await self._session.flush()
        return ClaimWithCodes(claim=claim, codes=code_rows)

    def _details_query(self, physician_id: int) -> Select:
        # Joins Patient for the name without filtering deleted_at — a soft-deleted
        # patient's name must still render on an existing claim. The run is outer-joined for
        # its encounter: a manual or purged claim has none.
        return (
            select(Claim, Patient.full_name, ExtractionRun.encounter_id)
            .join(Patient, Patient.id == Claim.patient_id)
            .outerjoin(ExtractionRun, ExtractionRun.id == Claim.extraction_run_id)
            .where(Claim.physician_id == physician_id, Claim.voided_at.is_(None))
            # id breaks ties: created_at comes from the DB clock, which SQLite only keeps
            # to the second.
            .order_by(Claim.service_date.desc(), Claim.created_at.desc(), Claim.id.desc())
        )

    async def _load_details(self, query: Select) -> list[ClaimDetail]:
        """Two round trips whatever the number of claims: the claims (with their patient's
        name), then every code row of those claims at once."""
        return await self._with_codes((await self._session.execute(query)).all())

    async def _with_codes(self, rows: Sequence) -> list[ClaimDetail]:
        """`rows` are `_details_query`'s (Claim, patient full name, encounter id)."""
        if not rows:
            return []
        code_rows = (
            await self._session.execute(
                select(ClaimCode).where(ClaimCode.claim_id.in_([row[0].id for row in rows])).order_by(ClaimCode.id)
            )
        ).scalars().all()
        codes_by_claim: dict[int, list[ClaimCode]] = {}
        for code_row in code_rows:
            codes_by_claim.setdefault(code_row.claim_id, []).append(code_row)

        return [
            ClaimDetail(
                claim=row[0], patient_full_name=row[1], codes=codes_by_claim.get(row[0].id, []), encounter_id=row[2]
            )
            for row in rows
        ]

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        patient_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        billed: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClaimDetail]:
        """`billed` filters on whether the claim is on a bill — which status that means is
        app/claims/status.py's call, not this repository's."""
        query = self._details_query(physician_id)
        if patient_id is not None:
            query = query.where(Claim.patient_id == patient_id)
        if date_from is not None:
            query = query.where(Claim.service_date >= date_from)
        if date_to is not None:
            query = query.where(Claim.service_date <= date_to)
        if billed is not None:
            query = query.where(Claim.bill_id.is_not(None) if billed else Claim.bill_id.is_(None))
        return await self._load_details(query.limit(limit).offset(offset))

    async def list_unbilled(self, physician_id: int) -> list[ClaimDetail]:
        """Every live claim not on a bill yet — no page limit: what's still to bill is
        counted and summed whole."""
        return await self._load_details(self._details_query(physician_id).where(Claim.bill_id.is_(None)))

    async def list_by_ids(self, physician_id: int, claim_ids: Sequence[int]) -> list[ClaimDetail]:
        """The requested live claims this physician owns — ids that don't exist, are voided
        or belong to another physician are simply absent from the result, so callers compare
        lengths."""
        if not claim_ids:
            return []
        return await self._load_details(self._details_query(physician_id).where(Claim.id.in_(claim_ids)))

    async def live_for_encounters(self, physician_id: int, encounter_ids: Sequence[int]) -> dict[int, ClaimDetail]:
        """Each encounter's live claim, from whichever of its runs it was saved — what the
        physician actually selected, not what the latest run proposed. Encounters without
        one are absent; if several runs were claimed, the most recent claim wins."""
        if not encounter_ids:
            return {}
        details = await self._load_details(
            self._details_query(physician_id).where(ExtractionRun.encounter_id.in_(encounter_ids))
        )
        by_encounter: dict[int, ClaimDetail] = {}
        # Newest first, so the first claim per encounter wins.
        for detail in details:
            by_encounter.setdefault(detail.encounter_id, detail)
        return by_encounter

    async def list_for_bill(self, bill_id: int, physician_id: int) -> list[ClaimDetail]:
        return await self._load_details(self._details_query(physician_id).where(Claim.bill_id == bill_id))

    async def get_for_physician(self, claim_id: int, physician_id: int) -> Claim | None:
        claim = await self._session.get(Claim, claim_id)
        if claim is None or claim.physician_id != physician_id or claim.voided_at is not None:
            return None
        return claim

    async def void(self, claim: Claim) -> None:
        """Whether this claim may be voided is app/claims/status.py's ClaimLifecycle's call."""
        claim.voided_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def attach_to_bill(self, claim_ids: Sequence[int], bill_id: int) -> None:
        """Attaches every claim or none: the UPDATE only matches live claims not already on
        a bill, so a claim another transaction billed or voided first is left out and the
        count comes up short."""
        if not claim_ids:
            return
        result = await self._session.execute(
            update(Claim)
            .where(Claim.id.in_(claim_ids), Claim.bill_id.is_(None), Claim.voided_at.is_(None))
            .values(bill_id=bill_id)
        )
        if result.rowcount != len(claim_ids):
            raise ClaimAlreadyBilledError()

    async def detach_from_bill(self, bill_id: int) -> None:
        await self._session.execute(
            update(Claim)
            .where(Claim.bill_id == bill_id)
            .values(bill_id=None)
        )

    async def get_live_by_extraction_run_id(self, extraction_run_id: int) -> Claim | None:
        result = await self._session.execute(
            select(Claim).where(Claim.extraction_run_id == extraction_run_id, Claim.voided_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def most_used_codes(self, physician_id: int, limit: int) -> list[str]:
        """The code numbers this physician bills most, over their live claims — most claims
        first, then most recently billed. Derived on every read rather than kept as a
        counter: it can never drift from the claims themselves."""
        result = await self._session.execute(
            select(ClaimCode.code)
            .join(Claim, Claim.id == ClaimCode.claim_id)
            .where(Claim.physician_id == physician_id, Claim.voided_at.is_(None))
            .group_by(ClaimCode.code)
            .order_by(func.count().desc(), func.max(Claim.service_date).desc(), ClaimCode.code)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_for_patient_on_date(self, physician_id: int, patient_id: int, service_date: date) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Claim)
            .where(
                Claim.physician_id == physician_id,
                Claim.patient_id == patient_id,
                Claim.service_date == service_date,
                Claim.voided_at.is_(None),
            )
        )
        return result.scalar_one()
