"""What every channel hands IntakeService: a note as its source sent it, plus the structured
facts the source knows about it. Administrative facts (patient identity, date, times,
place, author) come from these fields — never from the note text or the LLM."""

from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.intake.channels import Channel


class EncounterMeta(BaseModel):
    """Source facts that drive no query, stored as `encounters.encounter_meta`. Direct RAMQ
    submission will need most of them; the LLM only ever flags them as missing."""

    time_start: time | None = None
    time_end: time | None = None
    location_label: str | None = None
    etablissement_number: str | None = None
    # The note's author in the source system's own terms (a user id, a licence number...).
    # Also half of the deduplicator's fallback key when there's no external note id.
    author_ref: str | None = None
    referring_physician: str | None = None


class SourceNote(BaseModel):
    source_system: str = Field(min_length=1, max_length=64)
    channel: Channel
    external_note_id: str | None = Field(default=None, max_length=255)
    external_encounter_id: str | None = Field(default=None, max_length=255)
    signed_at: datetime | None = None
    nam: str | None = None
    # The source's own chart number — kept for a later manual match, never resolved on.
    mrn: str | None = None
    # A date, or the source's own string for one: parsed with the source's date_order
    # (app/intake/normalizers/), so "03/04/2026" means what that source means by it.
    service_date: date | str | None = None
    meta: EncounterMeta = Field(default_factory=EncounterMeta)
    text: str = Field(min_length=1)
    # Groups notes received together, e.g. one ER shift pasted at the end of the night.
    batch_label: str | None = Field(default=None, max_length=64)


class PastedNotes(BaseModel):
    """`POST /intake/notes`'s simple form: text as the physician pasted it — one note, or a
    whole ER shift the splitter cuts into one note per `**NAM :**` header."""

    text: str = Field(min_length=1)
    source_system: str = Field(default="manual", min_length=1, max_length=64)
    batch_label: str | None = Field(default=None, max_length=64)


class ReceiveOutcomeOut(BaseModel):
    """One received note's fate — app/intake/service.py's ReceiveOutcome, over HTTP."""

    outcome: str
    encounter_id: int
    patient_id: int | None
    enqueued: bool
