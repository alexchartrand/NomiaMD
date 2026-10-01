"""The NAM (numéro d'assurance maladie / RAMQ health insurance number) as a first-class
value object. Stdlib only — this is pure parsing/decoding logic with no DB or HTTP concerns.

A NAM is 3 letters of the surname + 1 letter of the given name + YYMMDD (the birth date,
with 50 added to the month for women) + a 2-digit sequence number, e.g. "DESR8102 1001" for
someone born 1981-02-10."""

import re
from dataclasses import dataclass
from datetime import date

from app.postgresdb import Gender

_NAM_RE = re.compile(r"^[A-Z]{4}\d{8}$")
_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
# Unlike _NAM_RE (a full-string validator for an already-isolated candidate token), this
# scans free-form prose for a NAM-shaped substring wherever it appears — tolerant of the
# spaced/hyphenated grouping the module docstring's own example uses ("DESR8102 1001") as
# well as the unspaced form the consultations/ fixtures actually use ("DESR81021001").
_EMBEDDED_NAM_RE = re.compile(r"\b[A-Za-z]{4}[\s-]?\d{4}[\s-]?\d{4}\b")

_MAX_PLAUSIBLE_AGE = 120
_CENTURIES = (1900, 2000)


@dataclass(frozen=True)
class NamIdentity:
    date_of_birth: date
    gender: Gender


def normalize(raw: str | None) -> str | None:
    """Uppercases and strips everything non-alphanumeric (NAMs are written spaced or
    hyphenated), then validates the result is exactly 4 letters followed by 8 digits.
    Returns None on anything malformed, which makes it safe to call on both LLM output and
    free-text roster values."""
    if not raw:
        return None
    candidate = _NOT_ALNUM_RE.sub("", raw).upper()
    return candidate if _NAM_RE.fullmatch(candidate) else None


def _age_at(birth: date, on_date: date) -> int:
    return on_date.year - birth.year - ((on_date.month, on_date.day) < (birth.month, birth.day))


def decode(nam: str, *, on_date: date, age_hint: float | None = None) -> NamIdentity | None:
    """Decodes a NAM's date of birth and gender from its YYMMDD segment (positions 4:10).
    Month 51-62 means female (subtract 50); month 01-12 means male; anything else is
    invalid. The two-digit year needs a century guess: both the 19xx and 20xx candidate
    dates are tried, any in the future or implying an age over 120 are discarded, and if
    more than one still remains, age_hint (when given) breaks the tie by picking the
    candidate within +/-1 year of it — never guessing a birth year ~100 years wrong."""
    normalized = normalize(nam)
    if normalized is None:
        return None

    month_field = int(normalized[6:8])
    if 51 <= month_field <= 62:
        gender = Gender.FEMALE
        month = month_field - 50
    elif 1 <= month_field <= 12:
        gender = Gender.MALE
        month = month_field
    else:
        return None

    yy = int(normalized[4:6])
    day = int(normalized[8:10])

    candidates: list[date] = []
    for century in _CENTURIES:
        try:
            candidate = date(century + yy, month, day)
        except ValueError:
            continue
        if candidate > on_date:
            continue
        if _age_at(candidate, on_date) > _MAX_PLAUSIBLE_AGE:
            continue
        candidates.append(candidate)

    if not candidates:
        return None
    if len(candidates) == 1:
        birth = candidates[0]
    else:
        if age_hint is None:
            return None
        within_hint = [c for c in candidates if abs(_age_at(c, on_date) - age_hint) <= 1]
        if len(within_hint) != 1:
            return None
        birth = within_hint[0]

    return NamIdentity(date_of_birth=birth, gender=gender)


def redact(text: str) -> str:
    """Masks any NAM-shaped substring in free-form text with "[NAM]". Used by
    app/ramq_codes/task.py before interpolating the raw transcript into the billing_codes
    prompt: render_for_billing_codes already strips the patient's name and NAM from the
    structured summary (app/summary/task.py), but the transcript now also reaches that
    prompt (see BillingCodesTask), and a NAM is a direct government identifier — this is a
    best-effort scrub, not a guarantee, so it errs toward over-matching rather than missing
    one."""
    return _EMBEDDED_NAM_RE.sub("[NAM]", text)
