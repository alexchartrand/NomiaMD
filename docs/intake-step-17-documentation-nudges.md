# Step 17 — Documentation nudges

**Phase:** 4 · **Depends on:** 11 · **Unblocks:** —
**Plan section:** §2 Optimizations (documentation nudges), §3 Administrative facts

## Goal
When a code needs a fact the note doesn't state (time, duration, place, referring
physician), tell the physician to **add it to the note** before billing. Never guess the fact
and never bill without it.

## Tasks
- [ ] Inventory which facts gate RAMQ code variants or submission:
  - from the summary: `EncounterSetting` (`time_start`, `time_end`, `duration_minutes` +
    `duration_explicitly_stated`, `location_detail`) in `app/summary/models.py`
  - from eligibility: the axes that end up in `needs_confirmation`
  - from submission: lieu/établissement, secteur, diagnosis, referring physician (the
    future RAMQ track)
- [ ] `app/intake/documentation_gaps.py`: a **deterministic** `DocumentationGapDetector` that
  takes the summary result, the billing result and `EncounterMeta` and returns a list of
  `DocumentationGap(fact, reason, suggestion_fr)`. Structured metadata from the source wins
  over the summary (for example, Epic's encounter times fill the time gap).
- [ ] Add `documentation_gaps` to `GET /encounters/{id}`. Gaps also block `all_clean`.
- [ ] Review UI: a "Note incomplète" box listing the gaps, for example "Ajoutez l'heure de début
  et de fin à la note : le code X exige une durée ≥ 30 min". If the note is amended, step 16
  re-extracts it.

## Done when
Unit tests cover each gap type from summary and metadata combinations, and that metadata wins
over the summary. An encounter with a gap is never `all_clean`.
