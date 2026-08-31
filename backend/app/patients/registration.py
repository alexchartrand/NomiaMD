"""Whether a patient is registered with a given physician is a derived fact, not a stored
one: it's an exact match between the patient's own `family_doctor_practice_number` and
that physician's `User.practice_number` — both RAMQ practice numbers, so an exact match is
as definitive as a NAM match (see app/patients/nam.py). Pure comparison, no I/O, so both
app/ramq_codes/context_builder.py (billing_codes' registration axis) and
app/patients/router.py (the API's read-only `is_registered_with_current_physician` field)
share one definition instead of two copies drifting apart."""


def resolve_registration(
    patient_practice_number: str | None, physician_practice_number: str | None
) -> bool | None:
    """None (unknown) whenever either side hasn't recorded a practice number — never guess
    registration status from an incomplete comparison. Otherwise True/False from the exact
    match."""
    if patient_practice_number is None or physician_practice_number is None:
        return None
    return patient_practice_number == physician_practice_number
