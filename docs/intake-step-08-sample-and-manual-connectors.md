# Step 08 — Sample and manual (paste/upload) connectors, ER shift paste

**Phase:** 2 · **Depends on:** 07 · **Unblocks:** 09, 11
**Plan section:** §4 connectors, §2 flow 3 (ER shift mode)

## Goal
Move today's two input paths (synthetic sample, pasted text) onto the intake core, and
support pasting a whole ER shift at once.

## Tasks
- [x] `app/intake/connectors/sample.py`: `SampleConnector` turns each
  `app/sample_patients/service.py` note into a `SourceNote`:
  - `source_system="simule"`, `channel=sample`
  - `external_note_id` = the sample's file id
  - NAM from the `**NAM :**` header (reuse `parse_header_fields`)
- [x] `app/intake/connectors/manual.py`: `ManualConnector.from_paste(text, source_system,
  batch_label=None) -> list[SourceNote]`.
  - `NoteSplitter` splits a multi-patient paste on recognizable boundaries (a NAM header line,
    or an explicit `---` separator). Each piece becomes its own `SourceNote`.
  - It pulls a NAM out of each piece with a regex plus `nam.normalize`. This is a **structured
    field match, not LLM inference**. If it's ambiguous, the NAM stays `None`.
  - All pieces of one paste share `batch_label` (for example "Urgence 2026-10-01 nuit").
- [x] Upload: `.txt`/`.md` only for now, read as text and passed to `from_paste`.
- [x] `scripts/seed_db.py`: seed one encounter per `consultations/` note for the demo
  physician, through `IntakeService` (so the seed exercises the real path).

## Done when
Tests cover:
- the sample connector on the real `consultations/` fixtures (NAM is parsed)
- the splitter: a single note, 3 notes with NAM headers, 2 notes with `---`, a note
  without a NAM
- the batch label propagates to every piece
- the seed creates N encounters, and re-running it creates 0 (dedup)

## Notes (done 10/1)
- Connectors live in `app/intake/connectors/` and are exported from `app.intake`.
  `SAMPLE_SOURCE_SYSTEM = "simule"` is what the frontend already sends.
- The sample connector also passes the `**Date/heure :**` header as `service_date`.
  `IntakeService` parses it with the source's `date_order`.
- NAM header reading is in its own module (`nam_header.py`, `read_header_nam`).
  `**NAM :** X`, `NAM : X` and `**NAM** : X` all match, and the value may carry trailing
  text. A NAM in the prose never counts. Two header lines with different NAMs → `None`.
- Splitter boundaries: a `---` line always cuts, even a Markdown rule inside one note.
  A paragraph with a NAM header cuts once the current piece already has a NAM, and the cut
  is at the start of that paragraph, so the clinic, physician and patient lines above the
  NAM stay with their note. A title above the first note stays with the first note.
- Upload is `ManualConnector.from_upload(filename, content, ...)`: `.txt`/`.md` only, UTF-8
  (a BOM is stripped), `channel=upload`. Anything else raises `UnsupportedUploadError`. The
  HTTP route is step 09.
- New `IntakeService.receive_all(notes, user)`: receives the notes in order, each one on
  its own. The seed uses it, and so will step 09's batch paste.
- `seed_db.py` now commits the user and patients first, then receives the samples through
  `IntakeService` with a queue that does nothing. Seeded encounters stay "reçu", so seeding
  spends no LLM calls, as before. A sample whose patient couldn't be created is no longer
  skipped: it is stored "à associer". The script still refuses to run twice (admin email
  exists), so the "re-run creates 0" case is tested on `receive_all` over the samples.
