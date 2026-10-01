"""Formats a "Surname, Given" name (the convention consultation notes and NAM-derived
identities state names in) into "Given Surname" for display/storage. Pure string logic,
shared by app/patients/verification.py (mismatch display) and scripts/seed_db.py (seeding
patients from consultation-note headers)."""


def format_full_name(name_as_stated: str | None) -> str | None:
    if not name_as_stated:
        return None
    if "," in name_as_stated:
        surname, given = name_as_stated.split(",", 1)
        return " ".join(part.strip() for part in (given, surname) if part.strip()) or None
    return name_as_stated.strip().title()
