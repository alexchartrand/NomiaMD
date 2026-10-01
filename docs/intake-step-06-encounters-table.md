# Step 06 — `encounters` table and repository

**Phase:** 2 (weeks 4–9) · **Depends on:** — · **Unblocks:** 07–11, 05's purge job
**Plan section:** §4 Data model

## Goal
Introduce the encounter as the unit the physician works on: one signed note from one
source. Note text moves out of `extraction_runs` and into it, so the encounter becomes the
single retention purge target.

## Tasks
- [ ] `Encounter` model in `backend/app/postgresdb/models.py`, table `encounters`:
  - `id`, `user_id` (FK users), `patient_id` (FK patients, **nullable**, RESTRICT)
  - `source_system` (String 64), `channel` (String 32 + CHECK, the same pattern as
    `claim_codes.confidence`)
  - `external_note_id`, `external_encounter_id` (nullable), `content_hash` (sha256 hex)
  - `service_date` (Date, nullable), `encounter_meta` (`_JSON`: times, location, établissement…)
  - `note_text` (Text), `superseded_by_id` (self-FK, nullable), `extraction_error` (Text,
    nullable: a fact that can't be derived), `purge_after` (indexed), timestamps
  - Partial unique index on `(user_id, source_system, external_note_id, content_hash)` where
    `external_note_id IS NOT NULL` (both dialects, like `ix_patients_ramq_number_active`)
  - Index on `(user_id, service_date, id)`. The `id` breaks ties, because SQLite timestamps are second-precision.
- [ ] `ExtractionRun`: add `encounter_id` (FK, `ondelete="CASCADE"`) and **remove `transcript`**.
  `ExtractionRecorder.save` takes `encounter_id` instead of `transcript`. `ClaimService` must
  not read the transcript (check it doesn't).
- [ ] `Claim`: add `source_note_hash` and `external_note_id`, snapshotted from the run's
  encounter at save time (same rule as the other claim snapshots).
- [ ] `EncounterRepository` (`app/postgresdb/repositories/encounters.py`, flush only):
  `create`, `get_for_user`, `list_for_day(user_id, day)`, `find_by_external(...)`,
  `set_patient`, `mark_superseded`, `record_extraction_error`.
- [ ] Derived status (no stored column): `reçu` (no run), `prêt` (a run, no live claim),
  `revu` (live claim), `modifié` (superseded), `échec` (error, no run), `à associer` (no
  patient). Put it in one function, `app/intake/status.py`, computed from a joined query.
- [ ] Keep `POST /extract` working: it creates an `Encounter` (channel `paste`, no external id)
  before running the pipeline. Its request and response stay unchanged for now.
- [ ] Delete `backend/nomiamd.db`, update `scripts/seed_db.py`, re-seed.

## Files
`backend/app/postgresdb/models.py`, `repositories/encounters.py` (new), `repositories/extractions.py`,
`backend/app/extraction/recorder.py`, `backend/app/extraction/router.py`, `backend/app/claims/service.py`,
`backend/scripts/seed_db.py`.

## Done when
- Repository tests (conftest `db_session`): unique index rejects a duplicate version, while a
  different hash is accepted; `list_for_day` ordering; every status derivation case.
- Deleting an encounter cascades to its runs and results, and the claim survives with
  `extraction_run_id = NULL` and its audit fields.
- `uv run pytest` passes. The existing extraction UI still works end to end with `make dev-fake`.
