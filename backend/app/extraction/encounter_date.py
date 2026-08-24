"""Parses the free-form 'encounter date' string consultation_summary extracts
(EncounterSetting.date) into a real date — or None when it can't be confidently parsed.
No default is ever substituted here: an unparsed date must surface to the physician as
unparsed, not silently become "today" (see docs/plans/billing-workflow.md, Part 3)."""

import re
from datetime import date

_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}

_ACCENTS = str.maketrans("éèêëàâäîïôöûüùç", "eeeeaaaiioouuuc")

_FRENCH_DATE_RE = re.compile(r"(\d{1,2})\s+([a-zéèêëàâäîïôöûüùç]+)\s+(\d{4})", re.IGNORECASE)
_SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_encounter_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    text = raw.strip()

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    match = _FRENCH_DATE_RE.search(text)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower().translate(_ACCENTS))
        if month is not None:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    match = _SLASH_DATE_RE.match(text)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    return None
