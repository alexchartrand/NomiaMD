"""`shift_claims` and their `shift_claim_codes` lines."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import ShiftClaim, ShiftClaimCode
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ShiftClaimCodeInput:
    code: str
    description: str
    origin: str
    hours: int
    hourly_fee: Decimal | None
    fee_amount: Decimal | None
    secteur_dispensation: str
    secteur_dispensation_label: str
    source: str


@dataclass
class ShiftClaimInput:
    physician_id: int
    shift_id: int
    service_date: date
    start_time: time
    end_time: time
    care_setting: str
    period: str
    work_site_name: str
    etablissement_number: str | None
    codes: Sequence[ShiftClaimCodeInput]


@dataclass
class ShiftClaimDetail:
    claim: ShiftClaim
    codes: list[ShiftClaimCode]


class ShiftAlreadyClaimedError(Exception):
    """The shift is already on another live claim — the partial unique index on shift_id is
    the backstop for two saves racing past ShiftClaimService's own check."""


class ShiftClaimAlreadyBilledError(Exception):
    """A requested shift claim was billed or voided after the caller checked it."""


class ShiftClaimRepository(SessionRepository):
    """Voided shift claims are invisible to every read here; nothing is ever hard-deleted."""

    async def create(self, data: ShiftClaimInput) -> ShiftClaimDetail:
        claim = ShiftClaim(
            physician_id=data.physician_id,
            shift_id=data.shift_id,
            service_date=data.service_date,
            start_time=data.start_time,
            end_time=data.end_time,
            care_setting=data.care_setting,
            period=data.period,
            work_site_name=data.work_site_name,
            etablissement_number=data.etablissement_number,
        )
        self._session.add(claim)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # SQLite names the column, Postgres the index; an FK violation names neither.
            message = str(exc.orig).lower()
            if "unique constraint" in message and ("shift_claims.shift_id" in message or "ix_shift_claims_shift_active" in message):
                raise ShiftAlreadyClaimedError() from exc
            raise
        code_rows = [ShiftClaimCode(shift_claim_id=claim.id, **vars(code)) for code in data.codes]
        self._session.add_all(code_rows)
        await self._session.flush()
        return ShiftClaimDetail(claim=claim, codes=code_rows)

    def _live(self, physician_id: int) -> Select:
        return (
            select(ShiftClaim)
            .where(ShiftClaim.physician_id == physician_id, ShiftClaim.voided_at.is_(None))
            # id breaks ties: created_at is second-precision on SQLite.
            .order_by(ShiftClaim.service_date.desc(), ShiftClaim.start_time.desc(), ShiftClaim.id.desc())
        )

    async def _with_codes(self, query: Select) -> list[ShiftClaimDetail]:
        claims = list((await self._session.execute(query)).scalars().all())
        if not claims:
            return []
        code_rows = (
            await self._session.execute(
                select(ShiftClaimCode)
                .where(ShiftClaimCode.shift_claim_id.in_([claim.id for claim in claims]))
                .order_by(ShiftClaimCode.id)
            )
        ).scalars().all()
        by_claim: dict[int, list[ShiftClaimCode]] = {}
        for row in code_rows:
            by_claim.setdefault(row.shift_claim_id, []).append(row)
        return [ShiftClaimDetail(claim=claim, codes=by_claim.get(claim.id, [])) for claim in claims]

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        billed: bool | None = None,
    ) -> list[ShiftClaimDetail]:
        query = self._live(physician_id)
        if date_from is not None:
            query = query.where(ShiftClaim.service_date >= date_from)
        if date_to is not None:
            query = query.where(ShiftClaim.service_date <= date_to)
        if billed is not None:
            query = query.where(ShiftClaim.bill_id.is_not(None) if billed else ShiftClaim.bill_id.is_(None))
        return await self._with_codes(query)

    async def list_by_ids(self, physician_id: int, claim_ids: Sequence[int]) -> list[ShiftClaimDetail]:
        """The requested live claims this physician owns; the others are absent."""
        if not claim_ids:
            return []
        return await self._with_codes(self._live(physician_id).where(ShiftClaim.id.in_(claim_ids)))

    async def list_for_bill(self, bill_id: int, physician_id: int) -> list[ShiftClaimDetail]:
        return await self._with_codes(self._live(physician_id).where(ShiftClaim.bill_id == bill_id))

    async def live_for_shift(self, shift_id: int, physician_id: int) -> ShiftClaimDetail | None:
        details = await self._with_codes(self._live(physician_id).where(ShiftClaim.shift_id == shift_id))
        return details[0] if details else None

    async def claimed_shift_ids(self, physician_id: int, shift_ids: Sequence[int]) -> set[int]:
        """Those of `shift_ids` with a live claim."""
        if not shift_ids:
            return set()
        result = await self._session.execute(
            select(ShiftClaim.shift_id).where(
                ShiftClaim.physician_id == physician_id,
                ShiftClaim.shift_id.in_(shift_ids),
                ShiftClaim.voided_at.is_(None),
            )
        )
        return set(result.scalars().all())

    async def get_for_physician(self, claim_id: int, physician_id: int) -> ShiftClaim | None:
        claim = await self._session.get(ShiftClaim, claim_id)
        if claim is None or claim.physician_id != physician_id or claim.voided_at is not None:
            return None
        return claim

    async def void(self, claim: ShiftClaim) -> None:
        claim.voided_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def attach_to_bill(self, claim_ids: Sequence[int], bill_id: int) -> None:
        """Every claim or none — same conditional UPDATE as ClaimRepository.attach_to_bill."""
        if not claim_ids:
            return
        result = await self._session.execute(
            update(ShiftClaim)
            .where(ShiftClaim.id.in_(claim_ids), ShiftClaim.bill_id.is_(None), ShiftClaim.voided_at.is_(None))
            .values(bill_id=bill_id)
        )
        if result.rowcount != len(claim_ids):
            raise ShiftClaimAlreadyBilledError()

    async def detach_from_bill(self, bill_id: int) -> None:
        await self._session.execute(update(ShiftClaim).where(ShiftClaim.bill_id == bill_id).values(bill_id=None))
