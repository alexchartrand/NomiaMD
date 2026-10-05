"""The physician's to-do counts, read off the inbox rows' derived statuses — never
recomputed from the database here."""

from app.dashboard.models import TaskCountsOut
from app.encounters.models import EncounterRowOut
from app.intake import EncounterStatus

# Everything still to act on: not billed yet, and not an outdated version of a note. Same
# set as the inbox's "à traiter" filter (frontend InboxPage/filters.ts).
TO_DO_STATUSES = frozenset(
    {EncounterStatus.RECU, EncounterStatus.PRET, EncounterStatus.A_ASSOCIER, EncounterStatus.ECHEC}
)


class TaskCounter:
    @staticmethod
    def count(rows: list[EncounterRowOut]) -> TaskCountsOut:
        def having(status: EncounterStatus) -> int:
            return sum(1 for row in rows if row.status == status)

        return TaskCountsOut(
            to_do=sum(1 for row in rows if row.status in TO_DO_STATUSES),
            to_review=having(EncounterStatus.PRET),
            approvable=sum(1 for row in rows if row.all_clean),
            to_associate=having(EncounterStatus.A_ASSOCIER),
            failed=having(EncounterStatus.ECHEC),
            extracting=having(EncounterStatus.RECU),
            possible_duplicates=sum(1 for row in rows if row.possible_duplicate_ids),
        )
