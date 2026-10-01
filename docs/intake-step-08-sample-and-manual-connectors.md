# Step 08 — Sample and manual (paste/upload) connectors, ER shift paste

**Phase:** 2 · **Depends on:** 07 · **Unblocks:** 09, 11
**Plan section:** §4 connectors, §2 flow 3 (ER shift mode)

## Goal
Move today's two input paths (synthetic sample, pasted text) onto the intake core, and
support pasting a whole ER shift at once.

## Tasks
- [ ] `app/intake/connectors/sample.py`: `SampleConnector` turns each
  `app/sample_patients/service.py` note into a `SourceNote`:
  - `source_system="simule"`, `channel=sample`
  - `external_note_id` = the sample's file id
  - NAM from the `**NAM :**` header (reuse `parse_header_fields`)
- [ ] `app/intake/connectors/manual.py`: `ManualConnector.from_paste(text, source_system,
  batch_label=None) -> list[SourceNote]`.
  - `NoteSplitter` splits a multi-patient paste on recognizable boundaries (a NAM header line,
    or an explicit `---` separator). Each piece becomes its own `SourceNote`.
  - It pulls a NAM out of each piece with a regex plus `nam.normalize`. This is a **structured
    field match, not LLM inference**. If it's ambiguous, the NAM stays `None`.
  - All pieces of one paste share `batch_label` (for example "Urgence 2026-10-01 nuit").
- [ ] Upload: `.txt`/`.md` only for now, read as text and passed to `from_paste`.
- [ ] `scripts/seed_db.py`: seed one encounter per `consultations/` note for the demo
  physician, through `IntakeService` (so the seed exercises the real path).

## Done when
Tests cover:
- the sample connector on the real `consultations/` fixtures (NAM is parsed)
- the splitter: a single note, 3 notes with NAM headers, 2 notes with `---`, a note
  without a NAM
- the batch label propagates to every piece
- the seed creates N encounters, and re-running it creates 0 (dedup)
