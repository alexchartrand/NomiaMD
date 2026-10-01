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
