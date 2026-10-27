"""Reads shift_codes.yaml into typed, validated codes — a malformed file fails at startup, not
on the first shift billed."""

from datetime import date, time
from decimal import Decimal
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.care_setting import CareSetting
from app.shift_claims.catalog.garde import GardeOption
from app.shifts import DayType

DEFAULT_CATALOG_PATH = Path(__file__).with_name("shift_codes.yaml")


class DatedFee(BaseModel):
    model_config = ConfigDict(frozen=True)

    effective_from: date
    per_quart: Decimal


class ShiftCodeSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    section: str
    page: int | None = None
    manual_rev: str


class HourWindow(BaseModel):
    """Local hours of a day; an end at or before the start is midnight (00:00 = 24 h)."""

    model_config = ConfigDict(frozen=True)

    start: time
    end: time


class ShiftCode(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: str = Field(pattern=r"^\d{5}$")
    description: str
    care_settings: frozenset[CareSetting] = Field(min_length=1)
    day_types: frozenset[DayType] = Field(min_length=1)
    window: HourWindow
    quart_hours: int = Field(gt=0, le=24)
    divisible_in_hours: bool
    secteur_dispensation: str = Field(pattern=r"^\d{2}$")
    # Empty: applies whatever the garde option. Never ACTE: à l'acte earns no forfait.
    garde_options: frozenset[GardeOption] = frozenset()
    fees: tuple[DatedFee, ...] = Field(min_length=1)
    source: ShiftCodeSource

    @field_validator("fees")
    @classmethod
    def _oldest_first(cls, fees: tuple[DatedFee, ...]) -> tuple[DatedFee, ...]:
        return tuple(sorted(fees, key=lambda fee: fee.effective_from))

    @field_validator("garde_options")
    @classmethod
    def _no_acte(cls, options: frozenset[GardeOption]) -> frozenset[GardeOption]:
        if GardeOption.ACTE in options:
            raise ValueError("à l'acte earns no forfait")
        return options

    def applies_to(self, care_setting: CareSetting, garde_option: GardeOption) -> bool:
        return care_setting in self.care_settings and (not self.garde_options or garde_option in self.garde_options)

    def fee_on(self, day: date) -> DatedFee | None:
        """The fee in effect on `day`; None before the first one."""
        in_effect = [fee for fee in self.fees if fee.effective_from <= day]
        return in_effect[-1] if in_effect else None

    @property
    def citation(self) -> str:
        page = f", p. {self.source.page}" if self.source.page is not None else ""
        return f"{self.source.section}{page} (manuel {self.source.manual_rev})"


class _CatalogFile(BaseModel):
    secteurs_dispensation: dict[str, str]
    codes: list[ShiftCode]

    @field_validator("codes")
    @classmethod
    def _unique(cls, codes: list[ShiftCode]) -> list[ShiftCode]:
        numbers = [code.number for code in codes]
        if len(numbers) != len(set(numbers)):
            raise ValueError("duplicate shift code number")
        return codes

    @model_validator(mode="after")
    def _known_secteurs(self) -> "_CatalogFile":
        for code in self.codes:
            if code.secteur_dispensation not in self.secteurs_dispensation:
                raise ValueError(f"{code.number}: unknown secteur de dispensation {code.secteur_dispensation}")
        return self


class ShiftCodeCatalog:
    """The curated shift codes, by number. Read once, on first use."""

    def __init__(self, path: Path = DEFAULT_CATALOG_PATH) -> None:
        self._path = path

    @cached_property
    def _file(self) -> _CatalogFile:
        return _CatalogFile.model_validate(yaml.safe_load(self._path.read_text(encoding="utf-8")))

    @cached_property
    def _codes(self) -> dict[str, ShiftCode]:
        return {code.number: code for code in self._file.codes}

    def secteur_label(self, secteur: str) -> str | None:
        """A secteur de dispensation's name, e.g. "07" -> "Service d'urgence"."""
        return self._file.secteurs_dispensation.get(secteur)

    def all(self) -> list[ShiftCode]:
        return list(self._codes.values())

    def get(self, number: str) -> ShiftCode | None:
        return self._codes.get(number)

    def for_care_setting(
        self, care_setting: CareSetting, garde_option: GardeOption = GardeOption.ACTE
    ) -> list[ShiftCode]:
        return [code for code in self._codes.values() if code.applies_to(care_setting, garde_option)]
