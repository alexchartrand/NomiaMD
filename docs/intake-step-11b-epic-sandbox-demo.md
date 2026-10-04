# Step 11b — Epic sandbox connector (demo with fake patients)

**Phase:** 2–3 (right after the inbox) · **Depends on:** 07, 09, 11 · **Unblocks:** demos; step 19 reuses its mapping
**Plan section:** §1b (access step 2: build against the Epic sandbox)

## Goal
Pull notes for Epic's **synthetic sandbox patients** (fhir.epic.com) into the inbox, so a demo
runs the real path end to end: Epic → intake → extraction → review → claim. No Santé
Québec approval is involved: the sandbox is open to any registered developer and has no real data.

## Tasks
- [x] Register the app on **fhir.epic.com** (free) and take the **non-production client id**.
  Choose the auth flow the sandbox supports for clinician-side reads of `DocumentReference`.
  Backend services (system-level, signed JWT) is the simplest for a server-side import, and
  standalone SMART launch is the alternative. **Verify in Epic's docs which one the sandbox allows for these resources.**
  The private key stays a secret (env/file outside the repo).
  *Done:* backend services (`BackendServicesTokenProvider`: RS384 client assertion,
  `client_credentials` grant, token cached until a minute before expiry). Key pair at
  `~/.config/nomiamd/epic-sandbox/`. fhir.epic.com no longer takes an uploaded certificate,
  only a **Non-Production JWK Set URL**. That URL is a public HTTPS address serving
  `scripts/epic_sandbox_jwks.py`'s output, and the assertion's `kid` (`EPIC_SANDBOX_KEY_ID`)
  names the key in it. Env vars are in `backend/.env.example`. The app needs these APIs selected: `Patient.Read (R4)`,
  `DocumentReference.Search (Clinical Notes) (R4)`, `Binary.Read (Clinical Notes) (R4)`,
  `Encounter.Read (R4)` and `Encounter.Search (R4)` (the last one only for the inventory).
- [x] **Inventory the sandbox first.** `scripts/epic_sandbox_inventory.py` prints the table;
  `--write` writes the roster, `--record <id>` saves raw responses. Results on 2026-10-03 are
  under "Sandbox inventory" below. List the test patients that have `DocumentReference`
  clinical notes with content, plus `Encounter` data. Record them in this file. If notes are
  sparse or very short, the demo shows the plumbing more than code quality. Say so in the
  demo script.
- [x] `app/intake/connectors/epic_fhir/` (a package: one class per module): an `EpicFhirClient` (base URL + token provider, both
  configurable) and an `EpicNoteMapper`, **written so step 19 reuses them unchanged**:
  - `DocumentReference` (`status=current`, `docStatus=final`) + `Binary` → text
    (`HtmlNormalizer`, `date_order="mdy"`)
  - `Encounter.period` → `meta.time_start/end`; `Encounter.location` → `location_label`
  - `DocumentReference.id` + `meta.versionId` → `external_note_id`
    *Deviation:* `external_note_id` is the id alone, and `meta.versionId` goes to
    `EncounterMeta.source_version`. Folding the version into the id would make an amended note
    look like an unrelated new one; the deduplicator already detects a new version by the
    same id with a different content hash (step 16 builds on that).
  - `EpicNoteReader` does the fetching (search, drafts dropped before any Binary is read,
    Encounter read failure → the note is kept without times); `EpicNoteMapper` is pure.
    Instants are converted to America/Montreal wall-clock times.
  - `Patient.identifier` → NAM through a pluggable `PatientIdentifierStrategy`
- [x] **Demo identity mapping.** Sandbox patients have US identifiers, not NAMs.
  `SandboxIdentifierStrategy` maps each sandbox patient's FHIR id to a **fake NAM** seeded as a
  demo patient (a small mapping file + `scripts/seed_db.py` creates those patients), so the
  normal NAM resolver works. Step 19 swaps this for the real Santé Québec identifier strategy.
  *Done:* `sandbox_patients.json` (next to the connector) is written by the inventory script.
  Each fake NAM is built from the sandbox patient's real name, birth date and sex, with
  sequence `99`, so age and sex decode as usual. Each patient also lists the exact
  `note_ids` to import (see the inventory below for why).
- [x] `EpicSandboxConnector(PullConnector)` (`PullConnector` in `connectors/base.py`): `fetch_signed_notes(user, since)` over the
  inventoried patient list. Every note gets `source_system="epic_sandbox"`, `channel=fhir_pull`.
- [x] Route `POST /intake/epic-sandbox/import` (session auth): fetch and `IntakeService.receive`
  each note, returning the outcomes. Re-importing creates no duplicates (step 07 dedup).
  Plus `GET /intake/epic-sandbox` (`{"patients": n}`), which the frontend reads to know the
  flag is on. Epic errors → 502.
- [x] Feature flag `EPIC_SANDBOX_ENABLED` (default off). Startup refuses the flag when the
  environment is marked production, so sandbox data never mixes with real data.
  *Done:* production is `APP_ENV=production` (new; default `development`). Startup also fails
  when the flag is on without a client id or key file.
- [x] Frontend: re-enable the "Epic" card in "Ajouter manuellement" as **"Epic — démo
  (sandbox)"**. It's shown only when the backend reports the flag on. "Importer les notes"
  calls the import route, then redirects to the inbox.
  *Done:* there was no Epic card left on the page, so it's a third tab next to "Coller" and
  "Téléverser un fichier", with the English/US-style caveat in its text.
- [x] Demo script (a short section at the end of this file): which sandbox patients to show, the
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

## Sandbox inventory (2026-10-03)

Backend services auth works against fhir.epic.com: client id + JWK Set URL (a public gist for
now, see BACKLOG.md) + `kid`. A new app took about 45 minutes to sync to the sandbox
(`invalid_client` until then).

**The sandbox is shared and writable.** Of 153 signed notes across Epic's 8 documented test
patients, most were posted through the API by other developers' apps (author "User
Interconnect" or "User Epic"). They include contract tests, daily pain-score bots, 24 KB
`xxxx` size probes and broken HTML (`<a href="null">null</a>`), and more arrive every day.
Importing "every signed note" would fill the inbox with junk. So the roster lists the
notes to import by id. The inventory proposes them with `DemoNoteSelector`: notes Epic
seeded under a family-medicine or emergency physician account, at least 250 characters,
the 6 longest per patient.

| Patient (FHIR id) | Born | Fake NAM | Selected notes |
|---|---|---|---|
| Theodore Mychart (`e63wRTbPfr1p8UW81d8Seiw3`) | 1948-07-07 | `MYCT48070799` | 6: five family-medicine progress notes (2006–2010) and one ED provider note (2009) |
| Camila Lopez (`erXuFYUfucBZaryVksYEcMg3`) | 1987-09-12 | `LOPC87591299` | 1: an empty progress-note template (2023) |

Derrick Lin, Elijah Davis, Linda Ross, Olivia Roberts and Warren McGinnis have only other
apps' notes or one-liners ("Arm should heal quickly."). Desiree Powell has only drafts.

Other things the real data showed:
- **Times.** Office-visit encounters have `period.start == period.end` at 05:00Z (Central
  midnight). That's Epic writing "a date, no time". The mapper reads a zero-length period
  as date-only, so it never invents a 01:00 visit. The ED encounter has real times
  (08:24–09:40 Montréal, "EMH Emergency").
- **No `meta.versionId`** on the sandbox's DocumentReferences, so `source_version` stays
  empty. Step 16 can't rely on it being present.
- The contract test (`uv run pytest -m epic_sandbox`) fails if a listed note disappears from
  the sandbox or stops being signed.

## Demo script

Setup (once): `EPIC_SANDBOX_ENABLED=true` and the `EPIC_SANDBOX_*` credentials in
`backend/.env`, a freshly seeded DB (`scripts/seed_db.py` creates the two sandbox patients),
then `make dev-fake` (or `make dev` for real codes).

1. **Ajouter manuellement → "Epic — démo (sandbox)" → Importer les notes.** The import reads
   the 7 notes from fhir.epic.com and lands on the inbox, filtered to `epic_sandbox` over
   all dates (the notes date from 2006–2023, which the default period would hide). Every
   row is matched to its patient through the fake NAM, with no manual pick.
2. **Import again.** The banner reports 7 duplicates and nothing new: dedup by
   DocumentReference id + content hash.
3. **Open the 2009-03-12 ED provider note** (cough, fever, rhonchi: pneumonia workup). It's
   the only one with real visit times and an ER location, the shape of a DSN shift note.
4. **Open the 2007-07-25 follow-up** (hypertension, GERD, hypothyroidism, medication review).
   It's a classic omnipraticien follow-up with several chronic problems.
5. **Talking point: the note says "70 year old", the patient is 58.** Theodore's sandbox
   birth date (1948) makes him 58 on 2006-07-07, and `BillingContext` uses that. Age
   comes from the patient record, never from the transcript.
6. **Open Camila's 2023 note.** It's an empty template ("No chief complaint on file").
   No codes is the right answer, and the review screen shows it as such.
7. Review and save a claim from any Theodore note, as for any other source.

Caveats to say out loud:
- The notes are in **English and US-style** (US problem-list codes like `[401.9]`,
  imperial units, US drug names). Extraction runs on them anyway. They show the plumbing
  (Epic → intake → extraction → review → claim), not code quality on a Québec note.
- The service dates are years old. A real RAMQ claim must be billed within 90 days, so
  don't present the saved claims as submittable.
- Expected codes per note: not recorded yet. Fill this in after the first `make dev` run
  with the real model.
