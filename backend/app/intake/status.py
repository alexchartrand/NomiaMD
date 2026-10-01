"""An encounter's status — derived, never stored, so it can't drift from the rows it
describes. Computed from EncounterRepository's joined query (EncounterActivity).

When several facts hold at once, the first rule below wins:

1. `modifié` — a newer version of the note exists; whatever was done on this one may no
   longer match what was signed.
2. `à associer` — no patient yet; nothing else can happen until one is picked.
3. `revu` — a live (non-voided) claim was saved from one of its runs.
4. `prêt` — extracted, waiting for the physician's review.
5. `échec` — the last extraction attempt failed and no run exists.
6. `reçu` — received, not extracted yet."""

from enum import StrEnum

from app.postgresdb import EncounterActivity


class EncounterStatus(StrEnum):
    RECU = "reçu"
    PRET = "prêt"
    REVU = "revu"
    MODIFIE = "modifié"
    ECHEC = "échec"
    A_ASSOCIER = "à associer"


def status_of(activity: EncounterActivity) -> EncounterStatus:
    encounter = activity.encounter
    if encounter.superseded_by_id is not None:
        return EncounterStatus.MODIFIE
    if encounter.patient_id is None:
        return EncounterStatus.A_ASSOCIER
    if activity.has_live_claim:
        return EncounterStatus.REVU
    if activity.has_run:
        return EncounterStatus.PRET
    if encounter.extraction_error is not None:
        return EncounterStatus.ECHEC
    return EncounterStatus.RECU
