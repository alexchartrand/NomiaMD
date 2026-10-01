"""Could two encounters be the same visit, received twice with different text (e.g. the
extension's capture and the scribe's note)? The deduplicator never merges those on its own
(see deduplicator.py); the inbox flags a pair this says yes to as "doublon possible" and
the physician confirms or dismisses it. A flag, not a decision — so it's derived from the
encounters each time, and only the physician's answer is stored (intake step 11).

A pair matches when nothing rules it out: same physician, same patient and same service
date (all known), and neither a different author nor start times too far apart. An unknown
author or time doesn't rule anything out."""

from datetime import datetime, time, timedelta

from app.postgresdb import Encounter

# Two notes of one visit can record slightly different start times (check-in vs. the
# moment the scribe started); further apart than this, they're two visits.
DEFAULT_TIME_TOLERANCE = timedelta(minutes=30)


class SameVisitMatcher:
    def __init__(self, time_tolerance: timedelta = DEFAULT_TIME_TOLERANCE) -> None:
        self._time_tolerance = time_tolerance

    def may_be_same_visit(self, a: Encounter, b: Encounter) -> bool:
        if a.id == b.id or a.user_id != b.user_id:
            return False
        if a.patient_id is None or a.patient_id != b.patient_id:
            return False
        if a.service_date is None or a.service_date != b.service_date:
            return False
        if _differ(_meta(a, "author_ref"), _meta(b, "author_ref")):
            return False
        start_a, start_b = _start_time(a), _start_time(b)
        if start_a is not None and start_b is not None:
            gap = abs(datetime.combine(a.service_date, start_a) - datetime.combine(a.service_date, start_b))
            if gap > self._time_tolerance:
                return False
        return True


def _meta(encounter: Encounter, field: str):
    return (encounter.encounter_meta or {}).get(field)


def _differ(a, b) -> bool:
    return a is not None and b is not None and a != b


def _start_time(encounter: Encounter) -> time | None:
    raw = _meta(encounter, "time_start")
    try:
        return time.fromisoformat(raw) if raw else None
    except ValueError:
        return None
