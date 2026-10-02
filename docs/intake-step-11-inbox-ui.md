# Step 11 — Inbox UI

**Phase:** 2 · **Depends on:** 09 (10 for real batch behaviour; done before 10, extraction inline) · **Unblocks:** daily use
**Plan section:** §2 flow 1, §4 Frontend

## Goal
The physician's daily screen: today's encounters, what's ready, what needs a patient, and a
one-click path for clean items.

## Tasks
- [x] `frontend/src/api/encounters.ts` and `intake.ts`: types written by hand to match step 09's
  Pydantic models. Export them from `api/index.ts`.
- [x] `frontend/src/pages/app/InboxPage/`:
  - Day picker (default today), counts header ("23 rencontres · 19 prêtes · 2 à associer").
  - Rows grouped by `batch_label` when present (ER shift), with a status chip per derived status.
  - "à associer" rows open an inline `PatientSearchSelect` (`components/PatientSearchSelect.tsx`),
    which calls `POST /encounters/{id}/patient`. "Créer un patient" reuses `CreatePatientForm`.
  - Clicking a `prêt` row opens the review. Reuse `ExtractionPage/ReviewStep.tsx` and
    `CodesReview.tsx` (extract them into shared components if they're too tied to the page).
  - **"Approuver les rencontres prêtes"** for `all_clean` rows. A confirm dialog lists them,
    then `POST /claims` runs per run. Never include rows with `needs_confirmation`.
  - `échec` rows get a "Réessayer" button (`POST /encounters/{id}/extract`).
  - Poll `GET /encounters` every ~15 s while any row is `reçu`.
- [x] **"Doublon possible"** — the same visit received twice with different text (e.g. the
  extension's capture and the scribe's note). Intake never merges those on its own (step 07),
  so the inbox asks:
  - Backend: `Encounter.duplicate_of_id` (self-FK, nullable) and `duplicate_dismissed_at`
    (nullable), stored only because they're the physician's decision. The flag itself is
    derived in `GET /encounters`: a pair `SameVisitMatcher.may_be_same_visit` accepts, where
    neither has been dismissed or confirmed. Delete the local DB and re-seed (no Alembic).
  - `POST /encounters/{id}/duplicate-of/{other_id}` (confirm: this one is hidden from the
    inbox and its extraction isn't billed) and `POST /encounters/{id}/not-duplicate`
    (dismiss: the flag doesn't come back). Both scoped to the physician's own encounters.
  - UI: a "doublon possible" badge on both rows, opening a side-by-side of the two notes
    with "Même visite" (pick which to keep) and "Visites distinctes".
  - Approve-all skips flagged rows until the physician answers.
- [x] `AppRouter.tsx`: add `/app/inbox` and make it the post-login landing page. Update the nav in `AppLayout.tsx`.
- [x] `ExtractionPage/SourceStep.tsx` becomes "Ajouter manuellement": a paste/upload form posting to
  `/intake/notes` (with an optional shift label), then redirecting to the inbox. Remove the
  disabled Telus card (the Epic card comes back as the sandbox demo in step 11b), and drop the separate sample picker (sample notes are seeded as
  encounters in step 08).

## Done when
- `npm run build` passes.
- With `make dev-fake` (inline extraction until step 10's worker), a seeded day shows encounters. Associating a patient moves the
  row to `prêt`. Approve-all creates claims visible in Facturation, and rows with
  `needs_confirmation` are excluded.
- Tests: two same-day visits with start times hours apart aren't flagged; a capture and a
  scribe note of one visit are; confirming hides one; dismissing clears the flag for good;
  approve-all skips flagged rows.

## Notes (done 10/1)
- Built before step 10: extraction runs inline (`InlineExtractionQueue`), so pasting notes
  and picking a patient wait on the LLM, and both buttons show that. Seeded encounters stay
  "reçu" (the seed queues nothing), so a `reçu` row with a patient gets an **"Extraire"**
  button (same `POST /encounters/{id}/extract` as "Réessayer"). The ~15 s polling while a
  row is `reçu` is in place but does nothing useful until the worker exists.
- **Not one day, a period** (asked for after the first pass: some physicians bill once a
  week). `GET /encounters?date_from=&date_to=` replaces `?date=`: both bounds included,
  either optional, none = every encounter; an undated encounter counts on the clinic day it
  was received. `EncounterRepository.list_in_period(user_id, EncounterPeriod)` replaces
  `list_for_day`. The inbox defaults to "Cette semaine" (Monday–Sunday), with presets
  (Aujourd'hui, Cette semaine, Semaine dernière, Ce mois-ci, Tout) and custom Du/au dates.
  Rows are grouped by day (most recent first), then by batch label within a day.
- Status ("À traiter" = reçu/prêt/à associer/échec, or one status), source and patient
  (masked name or NAM, accent-insensitive) filters run in the browser over the period's
  rows. Approve-all and the counts apply to the filtered rows. Period and filters live in
  the URL, and the encounter page's "back" returns to the same list.
- The seeded samples are dated from their headers (Feb.–Mar. 2026): pick "Tout" or their
  dates to see them.
- `all_clean` got stricter (`app/encounters/readiness.py`): besides high confidence and
  nothing to confirm, every code has at most one fee (otherwise approve-all would silently
  bill the first one), the encounter has a service date (a claim needs one), and it isn't
  flagged "doublon possible". Approve-all posts every code at `fee_index: null`, one claim
  at a time, and never overrides the same-patient-same-day warning (that row shows the
  error instead).
- Rows carry `extraction_run_id` and `possible_duplicate_ids`. The detail carries
  `duplicate_of_id`.
- Duplicates: `app/encounters/duplicates.py`. `DuplicateFlagger` pairs the day's
  encounters with `SameVisitMatcher`, skipping any already answered (confirmed or
  dismissed) and superseded versions (an amended note would otherwise match its own old
  version). `DuplicateDecisions` stores the answer. Confirming refuses to hide an encounter
  that already has a live claim (keep that one instead), or to keep one that is itself
  hidden. `GET /encounters` leaves hidden ones out. `POST /claims` refuses a run of a hidden
  encounter (409, plain detail; the frontend now treats only `duplicate_claim` 409s as the
  overridable warning).
- Dismissing is per encounter, not per pair (only one column): a third note matching a
  dismissed one later isn't flagged. Good enough until it happens in practice.
- Frontend: `/app/inbox` (landing), `/app/inbox/:encounterId` (note + review, read-only once
  reviewed, superseded or hidden), `/app/ajouter` (paste/upload, then back to the inbox
  with a "N notes reçues" banner). The review components moved from `ExtractionPage/` to
  `pages/app/review/`, with the save logic in `useCodeReview`. `ExtractionPage` and the
  frontend's sample picker are gone; `POST /extract` and `/sample-patients` stay on the
  backend (scripts use the former).
- **Reviewing a billed encounter again** (10/2): the inbox's code count is the live claim's
  codes once there is one (`ClaimRepository.live_for_encounters`), and the encounter detail
  carries that `claim`. The review page re-opens with the proposed codes, the claimed ones
  (and their fee and service date) ticked. A *brouillon* claim stays editable: saving calls
  `PUT /claims/{id}`, which voids it and saves the new selection from a run of the same
  encounter in one transaction (refused on a bill, 409; another encounter's run, 422). A
  *soumis* claim, a confirmed duplicate or a superseded note is read-only.
