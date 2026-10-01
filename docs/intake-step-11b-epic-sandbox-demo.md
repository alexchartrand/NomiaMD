# Step 11b — Epic sandbox connector (demo with fake patients)

**Phase:** 2–3 (right after the inbox) · **Depends on:** 07, 09, 11 · **Unblocks:** demos; step 19 reuses its mapping
**Plan section:** §1b (access step 2: build against the Epic sandbox)

## Goal
Pull notes for Epic's **synthetic sandbox patients** (fhir.epic.com) into the inbox, so a demo
runs the real path end to end: Epic → intake → extraction → review → claim. No Santé
Québec approval is involved: the sandbox is open to any registered developer and has no real data.

## Tasks
- [ ] Register the app on **fhir.epic.com** (free) and take the **non-production client id**.
  Choose the auth flow the sandbox supports for clinician-side reads of `DocumentReference`.
  Backend services (system-level, signed JWT) is the simplest for a server-side import, and
  standalone SMART launch is the alternative. **Verify in Epic's docs which one the sandbox allows for these resources.**
  The private key stays a secret (env/file outside the repo).
- [ ] **Inventory the sandbox first.** List the test patients that have `DocumentReference`
  clinical notes with content, plus `Encounter` data. Record them in this file. If notes are
  sparse or very short, the demo shows the plumbing more than code quality. Say so in the
  demo script.
- [ ] `app/intake/connectors/epic_fhir.py`: an `EpicFhirClient` (base URL + token provider, both
  configurable) and an `EpicNoteMapper`, **written so step 19 reuses them unchanged**:
  - `DocumentReference` (`status=current`, `docStatus=final`) + `Binary` → text
    (`HtmlNormalizer`, `date_order="mdy"`)
  - `Encounter.period` → `meta.time_start/end`; `Encounter.location` → `location_label`
  - `DocumentReference.id` + `meta.versionId` → `external_note_id`
  - `Patient.identifier` → NAM through a pluggable `PatientIdentifierStrategy`
- [ ] **Demo identity mapping.** Sandbox patients have US identifiers, not NAMs.
  `SandboxIdentifierStrategy` maps each sandbox patient's FHIR id to a **fake NAM** seeded as a
  demo patient (a small mapping file + `scripts/seed_db.py` creates those patients), so the
  normal NAM resolver works. Step 19 swaps this for the real Santé Québec identifier strategy.
- [ ] `EpicSandboxConnector(PullConnector)`: `fetch_signed_notes(user, since)` over the
  inventoried patient list. Every note gets `source_system="epic_sandbox"`, `channel=fhir_pull`.
- [ ] Route `POST /intake/epic-sandbox/import` (session auth): fetch and `IntakeService.receive`
  each note, returning the outcomes. Re-importing creates no duplicates (step 07 dedup).
- [ ] Feature flag `EPIC_SANDBOX_ENABLED` (default off). Startup refuses the flag when the
  environment is marked production, so sandbox data never mixes with real data.
- [ ] Frontend: re-enable the "Epic" card in "Ajouter manuellement" as **"Epic — démo
  (sandbox)"**. It's shown only when the backend reports the flag on. "Importer les notes"
  calls the import route, then redirects to the inbox.
- [ ] Demo script (a short section at the end of this file): which sandbox patients to show, the
  expected codes, and a caveat that sandbox notes are in English and US-style. The extraction
  runs on them anyway, so set the audience's expectations.

## Tests
- Unit: mapper on recorded sandbox JSON in `backend/tests/fixtures/epic/` (the sandbox data is
  synthetic, so recording it is fine). Signed note kept, draft dropped, times from Encounter,
  `mdy` date, the identifier strategy applied.
- Contract test against the live sandbox, marked `@pytest.mark.epic_sandbox` and excluded from the
  default `uv run pytest`.
- Flag tests: the route is 404 when the flag is off, and startup fails with the flag on in production.

## Done when
With the flag on and `make dev-fake` + the worker, "Importer les notes" puts the sandbox patients' notes
in the inbox as `prêt` (patients resolved through the fake NAMs). Review and claim then work as for any other source.

## Out of scope (stays in step 19)
EHR launch from inside Epic, per-user OAuth tokens, the real NAM identifier, amended-note
versioning, the production client id and Santé Québec activation.
