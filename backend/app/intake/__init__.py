"""Where notes come from: every source (paste, extension, scribe, DMÉ) ends up as an
Encounter, which the extraction pipeline then works on. Never imports ramq_codes.

Public interface — everything else that needs this imports it from here."""

from app.intake.channels import Channel
from app.intake.hashing import content_hash
from app.intake.status import EncounterStatus, status_of

__all__ = ["Channel", "EncounterStatus", "content_hash", "status_of"]
