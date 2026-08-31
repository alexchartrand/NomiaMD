"""Verifies the transcript's own stated identity against the patient chosen before
extraction ran, since the physician now picks the patient up front (see
app/extraction/pipeline.py) rather than the pipeline suggesting a roster match from the
transcript. Pure comparison — no repository, no DB, no FastAPI — this is a safety net
surfaced to the physician as a mismatch warning, never a gate that blocks anything itself.

A NAM is unique across every Quebec resident, so an exact hit/miss is definitive; name and
age comparisons are best-effort and tolerant (title-case/whitespace-insensitive names,
+/-1 year on age) since transcripts describe people in prose, not machine-normalized
fields."""

from dataclasses import dataclass
from datetime import date

from app.patients import nam
from app.patients.name_format import format_full_name
from app.postgresdb import Patient

_AGE_TOLERANCE_YEARS = 1.0


@dataclass(frozen=True)
class ExtractedIdentity:
    """Neutral over the extraction pipeline — deliberately does not import
    ConsultationSummaryResult, so this package stays extraction-agnostic."""

    ramq_number: str | None
    name_as_stated: str | None
    age_years: float | None
    age_months: float | None
    sex: str | None


@dataclass(frozen=True)
class PatientVerification:
    """Each `*_mismatch` field is None when the transcript didn't state enough to compare
    (no NAM/name/age mentioned), True when it disagrees with the chosen patient, and False
    when it agrees — never a guess."""

    extracted: ExtractedIdentity
    nam_mismatch: bool | None
    name_mismatch: bool | None
    age_mismatch: bool | None


def _age_years_on(date_of_birth: date, on_date: date) -> float:
    years = on_date.year - date_of_birth.year
    if (on_date.month, on_date.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return float(years)


def _nam_mismatch(extracted_ramq_number: str | None, patient_ramq_number: str | None) -> bool | None:
    normalized_extracted = nam.normalize(extracted_ramq_number)
    if normalized_extracted is None:
        return None
    return normalized_extracted != nam.normalize(patient_ramq_number)


def _name_mismatch(extracted_name_as_stated: str | None, patient_full_name: str) -> bool | None:
    formatted = format_full_name(extracted_name_as_stated)
    if formatted is None:
        return None
    return formatted.strip().casefold() != patient_full_name.strip().casefold()


def _age_mismatch(extracted: ExtractedIdentity, date_of_birth: date, on_date: date) -> bool | None:
    if extracted.age_years is not None:
        extracted_age = extracted.age_years
    elif extracted.age_months is not None:
        extracted_age = extracted.age_months / 12
    else:
        return None
    return abs(_age_years_on(date_of_birth, on_date) - extracted_age) > _AGE_TOLERANCE_YEARS


def verify_patient_identity(extracted: ExtractedIdentity, *, patient: Patient, on_date: date) -> PatientVerification:
    return PatientVerification(
        extracted=extracted,
        nam_mismatch=_nam_mismatch(extracted.ramq_number, patient.ramq_number),
        name_mismatch=_name_mismatch(extracted.name_as_stated, patient.full_name),
        age_mismatch=_age_mismatch(extracted, patient.date_of_birth, on_date),
    )
