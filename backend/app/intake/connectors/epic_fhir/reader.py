"""One patient's signed clinical notes from Epic, as SourceNotes: searches the patient's
notes, drops drafts, then fetches each kept note's body and encounter. Shared by the sandbox
connector and step 19's production one."""

import logging
from collections.abc import Callable
from datetime import date

from app.intake.connectors.epic_fhir.client import EpicFhirClient, Resource
from app.intake.connectors.epic_fhir.errors import EpicFhirError
from app.intake.connectors.epic_fhir.mapper import NOTE_CONTENT_TYPE, EpicNoteMapper
from app.intake.models import SourceNote

logger = logging.getLogger(__name__)


class EpicNoteReader:
    def __init__(self, client: EpicFhirClient, mapper: EpicNoteMapper) -> None:
        self._client = client
        self._mapper = mapper

    async def signed_notes(
        self, patient_id: str, since: date | None = None, include: Callable[[Resource], bool] | None = None
    ) -> list[SourceNote]:
        """`include`, when given, picks among the signed notes before any body is fetched."""
        patient = await self._client.read("Patient", patient_id)
        documents = await self._client.search(
            "DocumentReference", {"patient": patient_id, "category": "clinical-note"}
        )
        notes = []
        for document in documents:
            if include is not None and not include(document):
                continue
            note = await self._note(document, patient, since)
            if note is not None:
                notes.append(note)
        return notes

    async def _note(self, document: Resource, patient: Resource, since: date | None) -> SourceNote | None:
        if not self._mapper.is_signed(document):
            return None
        attachment = self._mapper.note_attachment(document)
        if attachment is None:
            logger.info("epic note without an HTML body skipped", extra={"document_id": document.get("id")})
            return None
        encounter = await self._encounter(document)
        service_date = self._mapper.service_date(document, encounter)
        if since is not None and service_date is not None and service_date < since:
            return None
        text = await self._client.binary_text(attachment["url"], NOTE_CONTENT_TYPE)
        if not text.strip():
            return None
        return self._mapper.to_source_note(document, text, patient, encounter)

    async def _encounter(self, document: Resource) -> Resource | None:
        """The note's encounter, or None when it has none or it can't be read — the note is
        still worth receiving; its times then show as missing rather than guessed."""
        reference = self._mapper.encounter_reference(document)
        if reference is None:
            return None
        try:
            return await self._client.read_reference(reference)
        except EpicFhirError as error:
            logger.warning(
                "epic encounter unreadable", extra={"reference": reference, "status_code": error.status_code}
            )
            return None
