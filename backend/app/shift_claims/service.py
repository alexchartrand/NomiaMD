"""Shift claim use cases: what a shift earns, saving the physician's confirmed codes as its
claim, and voiding a draft. Constructor-injected — wired by factory.py, no HTTP here."""

from datetime import date

from app.care_setting import parse_care_setting
from app.claims.status import ClaimLifecycle, ClaimStatus
from app.postgresdb import (
    Shift,
    ShiftAlreadyClaimedError,
    ShiftClaimInput,
    ShiftClaimRepository,
    ShiftRepository,
    WorkSite,
    WorkSiteRepository,
)
from app.care_setting import CareSetting
from app.shift_claims.catalog import GARDE_OPTION_LABELS_FR, GardeOption, ShiftCodeCatalog
from app.shift_claims.errors import (
    ShiftClaimConflictError,
    ShiftClaimNotFoundError,
    ShiftClaimOnBillError,
    ShiftNotFoundError,
)
from app.shift_claims.lines import ShiftClaimLineBuilder
from app.shift_claims.mapper import ShiftClaimMapper, ShiftCodeMapper
from app.shift_claims.models import GardeChoiceOut, ShiftBillingOut, ShiftClaimIn, ShiftClaimOut
from app.shift_claims.rules import ShiftCodeRules
from app.shifts import ShiftHours, ShiftMapper


class ShiftClaimService:
    def __init__(
        self,
        shifts: ShiftRepository,
        sites: WorkSiteRepository,
        claims: ShiftClaimRepository,
        catalog: ShiftCodeCatalog,
        rules: ShiftCodeRules,
        line_builder: ShiftClaimLineBuilder,
        code_mapper: ShiftCodeMapper | None = None,
        shift_mapper: ShiftMapper | None = None,
    ) -> None:
        self._shifts = shifts
        self._sites = sites
        self._claims = claims
        self._catalog = catalog
        self._rules = rules
        self._line_builder = line_builder
        self._code_mapper = code_mapper or ShiftCodeMapper(catalog)
        self._shift_mapper = shift_mapper or ShiftMapper()

    async def billing(self, user_id: int, shift_id: int, garde_option: GardeOption | None = None) -> ShiftBillingOut:
        """Under `garde_option` — by default the one its claim was saved under, else à l'acte."""
        shift, site = await self._owned_shift(user_id, shift_id)
        care_setting = parse_care_setting(shift.care_setting)
        claim = await self._claims.live_for_shift(shift.id, user_id)
        if garde_option is None:
            garde_option = GardeOption(claim.claim.garde_option) if claim is not None else GardeOption.ACTE
        suggested = self._rules.suggest(care_setting, _hours(shift), garde_option)
        return ShiftBillingOut(
            shift=self._shift_mapper.out(shift, site),
            garde_option=garde_option,
            garde_choices=self._garde_choices(care_setting),
            suggested=[self._code_mapper.suggested(line, shift.service_date) for line in suggested],
            available_codes=(
                [
                    self._code_mapper.available(code, shift.service_date)
                    for code in self._catalog.for_care_setting(care_setting, garde_option)
                ]
                if care_setting is not None
                else []
            ),
            claim=ShiftClaimMapper.from_detail(claim) if claim is not None else None,
        )

    def _garde_choices(self, care_setting: CareSetting | None) -> list[GardeChoiceOut]:
        if care_setting is None:
            return []
        forfaits = {
            option for code in self._catalog.all() if care_setting in code.care_settings for option in code.garde_options
        }
        if not forfaits:
            return []
        return [
            GardeChoiceOut(value=option, label=GARDE_OPTION_LABELS_FR[option])
            for option in GardeOption
            if option is GardeOption.ACTE or option in forfaits
        ]

    async def save(self, user_id: int, shift_id: int, body: ShiftClaimIn) -> ShiftClaimOut:
        """The shift's claim, created — or its draft replaced: the draft is voided and the new
        selection saved in its place, in the request's one transaction, so the voided one
        keeps what was first saved. A claim on a bill can't be replaced."""
        shift, site = await self._owned_shift(user_id, shift_id)
        hours = _hours(shift)
        care_setting = parse_care_setting(shift.care_setting)
        codes = self._line_builder.build(
            body.codes,
            care_setting=care_setting,
            hours=hours,
            suggested=self._rules.suggest(care_setting, hours, body.garde_option),
            garde_option=body.garde_option,
        )
        existing = await self._claims.live_for_shift(shift.id, user_id)
        if existing is not None:
            if not ClaimLifecycle.can_be_voided(existing.claim):
                raise ShiftClaimOnBillError()
            await self._claims.void(existing.claim)
        try:
            created = await self._claims.create(
                ShiftClaimInput(
                    physician_id=user_id,
                    shift_id=shift.id,
                    service_date=shift.service_date,
                    start_time=shift.start_time,
                    end_time=shift.end_time,
                    care_setting=shift.care_setting,
                    period=shift.period,
                    work_site_name=site.name,
                    etablissement_number=site.etablissement_number,
                    garde_option=body.garde_option.value,
                    codes=codes,
                )
            )
        except ShiftAlreadyClaimedError as exc:
            raise ShiftClaimConflictError() from exc
        return ShiftClaimMapper.from_detail(created)

    async def list_for_physician(
        self, user_id: int, *, date_from: date | None, date_to: date | None, status: ClaimStatus | None
    ) -> list[ShiftClaimOut]:
        details = await self._claims.list_for_physician(
            user_id,
            date_from=date_from,
            date_to=date_to,
            billed=ClaimLifecycle.is_billed(status) if status is not None else None,
        )
        return [ShiftClaimMapper.from_detail(detail) for detail in details]

    async def void(self, user_id: int, claim_id: int) -> None:
        claim = await self._claims.get_for_physician(claim_id, user_id)
        if claim is None:
            raise ShiftClaimNotFoundError()
        if not ClaimLifecycle.can_be_voided(claim):
            raise ShiftClaimOnBillError()
        await self._claims.void(claim)

    async def _owned_shift(self, user_id: int, shift_id: int) -> tuple[Shift, WorkSite]:
        shift = await self._shifts.get_for_user(shift_id, user_id)
        if shift is None:
            raise ShiftNotFoundError()
        # A deactivated site still names its past shifts.
        site = await self._sites.get_for_user(shift.work_site_id, user_id)
        if site is None:
            raise ShiftNotFoundError()
        return shift, site


def _hours(shift: Shift) -> ShiftHours:
    return ShiftHours(shift.service_date, shift.start_time, shift.end_time)
