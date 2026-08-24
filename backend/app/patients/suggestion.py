"""Identifies a physician's roster patient from an LLM-extracted identity, matched by NAM
only. A NAM is unique across every Quebec resident, so an exact hit is definitive — no
scoring, no threshold, no fuzzy name matching. Anything else (no NAM in the note, a
malformed one, or one that matches nobody on the roster) means no suggestion; the physician
either picks from the roster manually or creates the patient inline."""

import logging
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from app.patients import nam
from app.postgresdb import Gender, Patient, PatientRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedIdentity:
    """Neutral over the extraction pipeline — deliberately does not import
    ConsultationSummaryResult, so this package stays extraction-agnostic."""

    ramq_number: str | None
    name_as_stated: str | None
    age_years: float | None
    age_months: float | None
    sex: str | None


class PatientPrefill(BaseModel):
    """Values to prefill an inline patient-creation form with, derived from an extracted
    identity whether or not a roster match was found."""

    suggested_full_name: str | None = None
    suggested_ramq_number: str | None = None
    suggested_date_of_birth: date | None = None
    date_of_birth_is_estimated: bool
    suggested_gender: Gender | None = None


class PatientSuggestion(BaseModel):
    """`extracted`/`prefill` are what the note said (plus what is derived from it);
    `matched_patient_id` is the roster lookup. The two are independent — `extracted` is
    routinely present while `matched_patient_id` is null, which *is* the create-inline
    case, since the only way to get a match is an exact NAM hit."""

    extracted: ExtractedIdentity
    prefill: PatientPrefill
    matched_patient_id: int | None


def _suggested_full_name(name_as_stated: str | None) -> str | None:
    if not name_as_stated:
        return None
    if "," in name_as_stated:
        surname, given = name_as_stated.split(",", 1)
        return " ".join(part.strip() for part in (given, surname) if part.strip()) or None
    return name_as_stated.strip().title()


def _estimated_date_of_birth(*, on_date: date, age_years: float | None, age_months: float | None) -> date | None:
    if age_months is not None:
        total_months = on_date.year * 12 + (on_date.month - 1) - int(age_months)
        year, month = divmod(total_months, 12)
        return date(year, month + 1, 1)
    if age_years is not None:
        return date(on_date.year - int(age_years), 1, 1)
    return None


def _sex_to_gender(sex: str | None) -> Gender | None:
    if sex is None:
        return None
    normalized = sex.strip().lower()
    if normalized in ("m", "h", "homme", "male", "masculin"):
        return Gender.MALE
    if normalized in ("f", "femme", "female", "féminin", "feminin"):
        return Gender.FEMALE
    return None


def _build_prefill(extracted: ExtractedIdentity, *, on_date: date) -> PatientPrefill:
    normalized_nam = nam.normalize(extracted.ramq_number)
    if extracted.age_years is not None:
        age_hint = extracted.age_years
    elif extracted.age_months is not None:
        age_hint = extracted.age_months / 12
    else:
        age_hint = None
    decoded = nam.decode(normalized_nam, on_date=on_date, age_hint=age_hint) if normalized_nam else None

    if decoded is not None:
        return PatientPrefill(
            suggested_full_name=_suggested_full_name(extracted.name_as_stated),
            suggested_ramq_number=normalized_nam,
            suggested_date_of_birth=decoded.date_of_birth,
            date_of_birth_is_estimated=False,
            suggested_gender=decoded.gender,
        )

    return PatientPrefill(
        suggested_full_name=_suggested_full_name(extracted.name_as_stated),
        suggested_ramq_number=normalized_nam,
        suggested_date_of_birth=_estimated_date_of_birth(
            on_date=on_date, age_years=extracted.age_years, age_months=extracted.age_months
        ),
        date_of_birth_is_estimated=True,
        suggested_gender=_sex_to_gender(extracted.sex),
    )


class PatientSuggestionService:
    """Constructor-injected with PatientRepository (defaulted, so existing
    `PatientSuggestionService()` call sites don't need to change) — no FastAPI, no HTTP.
    Composition rather than inheriting PatientRepository: this class's job is NAM-matching
    and prefill logic, not being a patient repository itself."""

    def __init__(self, patient_repository: PatientRepository | None = None):
        self._patient_repository = patient_repository or PatientRepository()

    async def suggest(
        self, extracted: ExtractedIdentity, *, physician_id: int, on_date: date
    ) -> PatientSuggestion:
        prefill = _build_prefill(extracted, on_date=on_date)
        matched_patient_id = await self._match(extracted.ramq_number, physician_id=physician_id)
        return PatientSuggestion(extracted=extracted, prefill=prefill, matched_patient_id=matched_patient_id)

    async def _match(self, ramq_number: str | None, *, physician_id: int) -> int | None:
        normalized = nam.normalize(ramq_number)
        if normalized is None:
            return None

        roster: list[Patient] = list(await self._patient_repository.list_for_physician(physician_id))
        matches = [p for p in roster if nam.normalize(p.ramq_number) == normalized]

        if len(matches) == 1:
            return matches[0].id
        if len(matches) > 1:
            logger.warning(
                "Multiple roster patients share NAM %s for physician_id=%s — treating as no match.",
                normalized,
                physician_id,
            )
        return None
