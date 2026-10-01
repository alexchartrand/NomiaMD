# Step 07 — Intake core: `SourceNote`, normalizers, patient resolver, dedup, `IntakeService`

**Phase:** 2 · **Depends on:** 06 · **Unblocks:** 08, 09, 10
**Plan section:** §4 New bounded context `backend/app/intake/`

## Goal
A single entry point that every channel (paste, sample, extension, scribe, API pull) goes
through, turning "a note from somewhere" into a deduplicated encounter with its patient
resolved deterministically.

## Tasks
- [ ] `app/intake/models.py`:
  - `IntakeChannel` (StrEnum): `paste`, `upload`, `sample`, `extension`, `scribe_webhook`,
    `fhir_pull`, `partner_api`
  - `EncounterMeta`: `time_start`, `time_end`, `location_label`, `etablissement_number`,
    `author_ref`, `referring_physician`
  - `SourceNote` (Pydantic): `source_system`, `channel`, `external_note_id`,
    `external_encounter_id`, `signed_at`, `nam`, `mrn`, `service_date`, `meta`, `text`,
    `batch_label` (ER shift)
- [ ] `app/intake/normalizers/`: a `NoteNormalizer` ABC with `PlainTextNormalizer` and
  `HtmlNormalizer` (strip tags, keep paragraph breaks). The registry is keyed by `source_system`.
  Each normalizer also declares a `date_order` (`dmy` | `mdy`).
- [ ] `parse_encounter_date(raw, date_order="dmy")` in `app/extraction/encounter_date.py`.
  Pass the source's order through. This fixes the BACKLOG "MM/DD" item; check it off.
- [ ] `app/intake/patient_resolver.py`: `PatientResolver.resolve(nam) -> int | None` uses
  `app/patients/nam.py`'s `normalize`, then a new `PatientRepository.get_by_ramq_number`
  (active rows only). **Never** reads the note text and never calls the LLM. No NAM or an
  unknown NAM returns `None`, and the encounter shows as "à associer".
- [ ] `app/intake/deduplicator.py`: `content_hash` = sha256 of the normalized text. Outcomes:
  `new`, `duplicate` (same external id + hash), `new_version` (same external id, new hash),
  and a fallback match on `(patient, service_date, author_ref)` when there is no external id.
- [ ] `app/intake/queue.py`: an `ExtractionQueue` Protocol with `enqueue(encounter_id)`. For now,
  `InlineExtractionQueue` runs the pipeline directly (step 10 swaps in arq).
- [ ] `app/intake/service.py`: `IntakeService.receive(note, user) -> ReceiveOutcome`. Normalize,
  dedupe, resolve the patient, create the encounter, and enqueue when a patient is resolved.
  `new_version` handling is left as a TODO for step 16.

## Done when
Unit tests cover:
- each normalizer
- `date_order` for both orders
- the resolver: match, no NAM, malformed NAM, unknown NAM, soft-deleted patient
- each dedup outcome
- that `receive` enqueues only when the patient is resolved

`app/intake` imports nothing from `ramq_codes` (the bounded-context rule).
