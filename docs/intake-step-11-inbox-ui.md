# Step 11 — Inbox UI

**Phase:** 2 · **Depends on:** 09 (10 for real batch behaviour) · **Unblocks:** daily use
**Plan section:** §2 flow 1, §4 Frontend

## Goal
The physician's daily screen: today's encounters, what's ready, what needs a patient, and a
one-click path for clean items.

## Tasks
- [ ] `frontend/src/api/encounters.ts` and `intake.ts`: types written by hand to match step 09's
  Pydantic models. Export them from `api/index.ts`.
- [ ] `frontend/src/pages/app/InboxPage/`:
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
- [ ] **"Doublon possible"** — the same visit received twice with different text (e.g. the
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
- [ ] `AppRouter.tsx`: add `/app/inbox` and make it the post-login landing page. Update the nav in `AppLayout.tsx`.
- [ ] `ExtractionPage/SourceStep.tsx` becomes "Ajouter manuellement": a paste/upload form posting to
  `/intake/notes` (with an optional shift label), then redirecting to the inbox. Remove the
  disabled Telus card (the Epic card comes back as the sandbox demo in step 11b), and drop the separate sample picker (sample notes are seeded as
  encounters in step 08).

## Done when
- `npm run build` passes.
- With `make dev-fake` + worker, a seeded day shows encounters. Associating a patient moves the
  row to `prêt`. Approve-all creates claims visible in Facturation, and rows with
  `needs_confirmation` are excluded.
- Tests: two same-day visits with start times hours apart aren't flagged; a capture and a
  scribe note of one visit are; confirming hides one; dismissing clears the flag for good;
  approve-all skips flagged rows.
