"""How a note reached us. Stored as its value in `encounters.channel` (String + CHECK —
keep ck_encounters_channel in app/postgresdb/models.py in sync with this list)."""

from enum import StrEnum


class Channel(StrEnum):
    PASTE = "paste"
    UPLOAD = "upload"
    EXTENSION = "extension"
    SCRIBE_WEBHOOK = "scribe_webhook"
    FHIR_PULL = "fhir_pull"
    PARTNER_API = "partner_api"
    SAMPLE = "sample"
