# Plan — Encounter intake: where the notes come from (2026-10-01)

## Context

Today the only way a note enters NomiaMD is a physician pasting it into the form or picking a
synthetic `consultations/` sample. "Epic" and "Telus Health" are greyed out in the UI
(`frontend/src/pages/app/ExtractionPage/SourceStep.tsx`), `ExtractionRequest.source` is a
free-text tag (`backend/app/extraction/models.py`), and the physician must pick the patient
by hand before every extraction. To be usable day-to-day, NomiaMD has to pull signed notes from
the systems Quebec family doctors already use. It should pre-extract the codes in the
background and hand the physician a review queue, without breaking the invariants in CLAUDE.md.

### Decisions already made (Q&A, 2026-10-01)
| Topic | Decision |
|---|---|
| Settings | Clinic/GMF (DMÉ) **and** ER/hospital (Epic DSN) |
| Pilot | None yet. Choosing the first DMÉ depends on recruiting a pilot clinic |
| Billing source of truth | The **signed clinical note**, not the raw scribe transcript |
| V1 scope | **Phased**: low-friction channels now, official APIs in parallel |
| Review timing | **Both**: end-of-day batch queue by default, on-demand per encounter |
| Downstream | **Direct RAMQ submission** (separate track, but intake must capture the fields it needs) |
| LLM hosting | **Canadian/local only** for real data. This gates go-live |
| AI scribes | **Integration target too** (secondary channel) |
| Browser extension | **OK as a bridge** until each vendor's official API is signed |
| Capacity | Solo dev, full-time |
| Depth | Strategy + codebase design |

---

## 1. Sources, APIs and how to get access

### 1a. DMÉs (certified for omnipraticiens by MSSS)
| System | Vendor | Integration surface | How to get access | Priority |
|---|---|---|---|---|
| **Omnimed** | Omnimed (QC) | No public API documented. It has an established **"pre-billing system" launch hook** that already hands physician, billing location, patient (NAM, name) and date to Xacte, FACNET, MultiD, Softinfo, FMP and Fonds FMOQ. Plume IA reaches it through a Chrome extension (`*.omnimed.com` host permission). | Apply to become a **pre-billing partner**. That is the exact slot NomiaMD fits. A pilot clinic asking for it speeds this up. Bridge: browser extension. | **1** (most natural fit) |
| **Medesync** | TELUS Santé | **TELUS CHR Enterprise API** (GraphQL, RS512 JWT bearer, 15-min expiry; patients, appointments, encounters, clinical documents) plus the **TELUS Patient Chart FHIR R4 IG** (simplifier.net). TELUS lists 20+ partners (Plume, Tali, Heidi, FACNET, Nestor). AutoScribe pushes notes into Medesync. | Apply through TELUS Health's EMR add-on/partner program and sign the API agreement. **Verify** that the CHR Enterprise API covers Medesync clinic data and not only the CHR product. Bridge: browser extension (Medesync is 100 % web). | **1** |
| **MYLE** | MEDFAR | **No public API.** Third parties (Scribeberry) use Chrome extensions. MEDFAR bought CoeurWay and says its built-in AI will "support billing", which makes it a **competitor**. | Extension only. Partnership unlikely in the short term. | 3 |
| Ofys / MobileMed / Kinlogix / Toubib | Info-Data / MediSolution / TELUS | Unknown. Likely desktop or legacy. | Defer until a pilot clinic uses one. | 4 |

### 1b. Epic: Santé Québec's *Dossier santé numérique* (DSN)
- **Status:** Santé Québec runs it, not individual clinics. Live since 2026-05-09 in two pilot regions only (CIUSSS Mauricie–Centre-du-Québec and CIUSSS Nord-de-l'Île-de-Montréal), with a provincial rollout that "won't necessarily reach everywhere". Family doctors meet it during **ER, hospitalisation, and some GMF-U/CLSC** work.
- **API:** Epic on FHIR R4 with **SMART on FHIR** launch inside the clinician workspace (patient, encounter and user context passed in). Relevant resources:
  - `DocumentReference` + `Binary` for the signed progress/ED notes
  - `Encounter` for times and department/location
  - `Patient` for the NAM as an identifier
  - `Practitioner`
  - `Appointment`
  - CDS Hooks (optional, later)
- **Access steps:**
  1. Register the app on **fhir.epic.com** (free; you get a non-prod client id and a production id that stays inert).
  2. Build against the Epic sandbox using synthetic patients.
  3. Get a **customer (Santé Québec) to activate the production client id**. Expect a security review, a privacy impact assessment (**ÉFVP**), and possibly MSSS certification/homologation. Plan on 6–18 months.
  4. Optional: Vendor Services ($1,900/yr) and a Showroom/Connection Hub listing ($500/yr, only once live at one customer).
- **Bridge limitation:** Epic's clinician client (Hyperspace/Hyperdrive) is **not a normal browser tab**, so the extension bridge won't work. Until SMART on FHIR is approved, the ER channel is **copy/paste** with source-aware parsing (US date formats, English templates).

### 1c. AI scribes (secondary channel)
Certified in Quebec's AI transcription program: Plume IA, CoeurWay, AutoScribe (Mutuo), Tali AI, Heidi Santé Canada, Scribe MD, MedAssistant, AICA, NoteGen. Plume IA and CoeurWay hold most of the market, with roughly 2–3k physicians each.
- **Plume IA** (Quebec, GMF-focused, Omnimed and TELUS partner): **best first scribe partner.** Ask for a "Send to NomiaMD" action or webhook when the note is finalized.
- **AutoScribe, Tali, Heidi:** already integrate with Medesync, so their APIs and webhooks exist. Next in line.
- **CoeurWay:** owned by MEDFAR (competitor). Skip.
- **Rule:** a scribe note only counts as billable input once the physician has **finalized** it. The claim records `channel=scribe`, and the physician attests that it matches the chart. This keeps the "signed note" decision intact.

### 1d. Prerequisites common to every partnership (start now)
- **A pilot clinic.** Vendors prioritize integrations their own clinics ask for. Recruit 1–2 GMFs, ideally on Omnimed or Medesync, and let the pilot's DMÉ pick the first connector.
- **Law 25 package:**
  - a designated privacy officer
  - an ÉFVP template
  - an incident register
  - a service agreement (*mandataire*) with each clinic
  - data minimisation and retention rules (closes the 🔴 `extraction_runs` purge item in BACKLOG)
  - NAM encryption (BACKLOG item)
  - confirm with counsel whether the *Loi sur les renseignements de santé et de services sociaux* applies to private GMFs
- **Security posture:** Canadian hosting, a security questionnaire or SOC 2 roadmap, and cyber insurance.
- **A Canadian/local LLM in production** (see §3).

---

## 2. Physician workflow

**Current flow:** pick the source → pick the patient by hand → paste the note → wait ~2 LLM calls → review → save the claim. That is one encounter at a time, with manual identity entry.

**Target flows:**
1. **End-of-day inbox (default):**
   - Signed notes arrive throughout the day, through a connector pull, extension capture, scribe push or paste.
   - The patient is **auto-resolved by NAM** from the source's structured data.
   - Extraction runs in the background, so codes are already waiting.
   - The physician clears a queue, *"Aujourd'hui: 23 rencontres, 19 prêtes"*. When every code is high-confidence and nothing `needs_confirmation`, an **"Approuver"** fast path lets them approve in one click.
2. **In-context, per encounter:**
   - Omnimed's pre-billing button, a SMART launch inside Epic, or the extension side panel opens NomiaMD with the patient and note already filled in. The codes show while the chart is still open.
   - Same backend path as the inbox, just triggered on demand.
3. **ER shift mode (Epic, before API access):**
   - Paste several notes at the end of a shift. They are split per patient and grouped as one shift, and the shift is reviewed together.
4. **Scribe push:**
   - When the physician finalizes a note in the scribe, it lands in the inbox like any other source.

**Optimizations across all flows:**
- **Pre-extract, don't wait.** Run the LLM before the physician opens the item.
- **Patient auto-match by NAM** (deterministic). The physician only picks a patient when the NAM is missing or unknown, and can create the patient from the source's demographics.
- **Documentation nudges.** When a code variant needs a fact the note lacks (time stated, duration, place), say *"ajoutez l'heure à la note"* **before** billing. Never guess the fact.
- **Billing deadline tracker.** Flag encounters approaching RAMQ's submission deadline. **Verify** the current delay in the omnipraticien manual.
- **Dedup.** The same encounter can arrive through two channels (for example extension + scribe). It shows once in the inbox.

---

## 3. Other concerns

- **Data residency (gating).** Real notes must not leave Canada. Two things are affected:
  - *Chat calls:* `app/extraction/engine.py` calls the Mistral API. Replace it with an **OpenAI-compatible endpoint** (vLLM or TGI) serving an open-weight model on Canadian GPUs. Candidates: OVHcloud Beauharnois QC, AWS ca-central-1, Azure Canada Central, or Cohere on Canadian infrastructure.
  - *Query-time embeddings:* retrieval embeds text derived from the transcript, so it also hits Mistral today. The embedding model must run locally, and **ramq-ingestion must re-embed the codes and documents tables with the same model** (a cross-repo change).
  - Evaluate with `scripts/eval_extraction.py` on **2+ cases** before switching (per the retrieval-tuning memory).
- **Administrative facts come from structured source data, never from the LLM.** This extends the existing invariant to:
  - patient identity (NAM)
  - encounter start/end times
  - location/établissement number
  - service date
  - author practitioner

  Direct RAMQ submission will also need fields the summary doesn't capture reliably: lieu/établissement, secteur, times, diagnosis (CIM-9), and the referring physician. Connectors should supply these as structured metadata. The LLM only flags when they are missing.
- **Amended notes.** Signed notes get addenda. Version every source note (`external_note_id` + content hash). A new version re-runs extraction and **flags any existing claim** for re-review instead of silently changing it.
- **Audit vs retention.** RAMQ audits need proof of what was billed from what. Store `source_system`, the external ids and the note hash on the claim, so the text itself can still be purged.
- **Source-specific parsing.** Epic dates may be MM/DD (the open BACKLOG item in `encounter_date.py`), Epic templates are often in English, and DOM captures contain HTML/RTF. Each source needs its own normalizer.
- **Multi-encounter documents.** An ER shift paste or a CHSLD round holds several patients and has to be split.
- **Prompt injection** (BACKLOG item). This matters more once external systems push text automatically.
- **Extension risk:**
  - DOM changes break capture, so each DMÉ gets its own adapter, with snapshot tests and error telemetry.
  - Possible vendor terms-of-service conflict: retire the extension per vendor once the official API is signed.
  - Device auth: the extension uses a scoped token, not the session cookie.
- **Competition.** MYLE+CoeurWay is moving into billing, billing agencies are adding AI, and Epic sells its own coding tools. Being multi-DMÉ and including the physician review step is the differentiator.
- **Direct RAMQ submission.** Becoming a RAMQ-recognized billing software developer (conform to RAMQ technical specifications and SYRA) is its **own plan**. This plan only makes sure intake captures what that plan will need.

---

## 4. Codebase design

### New bounded context `backend/app/intake/`
"Where notes come from". It never imports `ramq_codes`. It hands off to the existing pipeline.

| File | Responsibility |
|---|---|
| `models.py` | `SourceNote` (Pydantic). Fields: `source_system`, `channel` (`paste`, `upload`, `extension`, `scribe_webhook`, `fhir_pull`, `partner_api`, `sample`), `external_note_id`, `external_encounter_id`, `content_hash`, `signed_at`, `author_ref`, `patient_identifiers` (NAM, MRN), `encounter_meta` (start/end, location, établissement), `text` |
| `connectors/base.py` | `PullConnector` ABC: `fetch_signed_notes(physician, since) -> list[SourceNote]`. Push channels don't need a connector; they call `IntakeService.receive` |
| `connectors/sample.py` | Wraps `app/sample_patients/service.py` as a source. Replaces the special "simulé" path |
| `connectors/manual.py` | Paste/upload. Splits multi-patient pastes |
| `connectors/epic_fhir.py`, `connectors/telus_chr.py` | Later phases |
| `normalizers/` | One normalizer per source: HTML/RTF → text, date-format hint passed into `parse_encounter_date` (fixes the BACKLOG MM/DD item) |
| `patient_resolver.py` | `PatientResolver`: canonical NAM via `app/patients/nam.py` → `PatientRepository` lookup. Returns `patient_id` or `None` (manual pick needed). Deterministic, no LLM |
| `deduplicator.py` | Idempotency on `(source_system, external_note_id, content_hash)`, falling back to `(patient, service_date, author)` |
| `service.py` | `IntakeService.receive(SourceNote, user)`: normalize → dedupe → resolve patient → upsert `Encounter` → enqueue extraction |
| `router.py` | `POST /intake/notes` (paste, extension, scribe; scribe and extension authenticate with scoped tokens or HMAC). `GET /encounters?date=` (inbox). `POST /encounters/{id}/patient` (manual pick). `POST /encounters/{id}/extract` (on-demand) |

### Data model (`backend/app/postgresdb/models.py`, plus one repository module per aggregate)
- **New `encounters` table:**
  - `user_id`, `patient_id` (nullable until resolved)
  - `source_system`, `channel`
  - `external_note_id`, `external_encounter_id`, `content_hash`, `note_version`
  - `service_date`, `encounter_meta` JSON
  - `note_text`
  - `superseded_by_id`, `purge_after`
- **`encounters` becomes the retention purge target.** Note text moves from `extraction_runs.transcript` to `encounters.note_text`. `extraction_runs` gains `encounter_id` (FK, cascade).
- **Status is derived, not stored:** no run means `reçu`, a run means `prêt`, a live claim means `revu`, a newer version means `modifié`. This follows the "prefer derived facts" feedback.
- **`claims` gains** `source_note_hash` and `external_note_id` for the audit trail.
- No Alembic: delete the local DB and re-seed (`scripts/seed_db.py` also seeds encounters from `consultations/`).

### Background extraction
- Add **`arq`** as the worker. It is asyncio-native, and Redis is already in docker-compose for rate limiting.
- `extract_encounter(encounter_id)` reuses `run_billing_codes_pipeline` (`app/extraction/pipeline.py`) and `ExtractionRecorder` (`app/extraction/recorder.py`) unchanged, except that the recorder takes `encounter_id`.
- `/extract` stays as the synchronous on-demand path, keyed by encounter.
- The composition root stays in `app/bootstrap.py`. Add `make worker`.

### LLM provider abstraction
- In `app/extraction/engine.py` and `app/llm/embeddings.py`, introduce `ChatModel` and `EmbeddingModel` interfaces with an `OpenAICompatible` implementation.
- Generalize `MISTRAL_ENDPOINT` to `LLM_ENDPOINT` and `EMBEDDING_ENDPOINT`. The fake LLM server keeps working.

### Browser extension (new top-level `extension/`)
- Manifest V3, TypeScript.
- One content-script adapter per DMÉ: `adapters/omnimed.ts`, `adapters/medesync.ts`, `adapters/myle.ts`. Each extracts the signed note, NAM, date and times from the DOM into a `SourceNote`, then posts to `/intake/notes`.
- A side panel shows the codes (per-encounter flow).
- Auth: a device token from a new `POST /auth/device-tokens` endpoint (scope `intake:write`), managed on the Profile page.

### Frontend
- New **`pages/app/InboxPage/`**: day picker, status chips, an "à associer" patient picker, approve-all for clean items. It reuses `CodesReview.tsx` and `ReviewStep.tsx`.
- `SourceStep.tsx` becomes the "Ajouter manuellement" entry point (paste/upload) and creates an encounter.
- Add `src/api/intake.ts` and `src/api/encounters.ts`, with types kept in sync by hand.

---

## 5. Roadmap (solo, full-time)

| Weeks | Product track | Partnership/compliance track (background) |
|---|---|---|
| 1–4 | LLM provider abstraction; Canadian-hosted model and local embeddings proof of concept; eval on 2+ cases | Recruit pilot GMF(s); privacy counsel; ÉFVP template; find the Santé Québec DSN contact; apply to TELUS and Omnimed partner programs; contact Plume IA |
| 4–9 | `app/intake` core, `encounters` table, NAM resolver, dedup, arq worker, sample and paste connectors, inbox UI | Coordinate the ramq-ingestion re-embed with the local model |
| 9–14 | **Epic sandbox demo connector** (fake patients, first); browser extension with the **pilot clinic's DMÉ** adapter; side panel; device tokens | Pilot clinic agreement; ÉFVP signed |
| 14–18 | Scribe webhook channel (first partner); amended-note versioning; documentation nudges | Scribe partner agreement |
| 18+ | Official connectors as approvals land: Omnimed pre-billing hook, TELUS CHR/FHIR, Epic production integration (reuses the sandbox connector; live when Santé Québec activates) | Santé Québec DSN process; start the separate RAMQ developer-recognition plan |

## 6. Verification
- **Backend unit tests** (conftest stubs, no network), covering:
  - each connector and normalizer against synthetic fixtures (FHIR `DocumentReference` JSON, saved DMÉ HTML snapshots)
  - `PatientResolver` (match, no NAM, unknown NAM)
  - dedup and idempotency
  - amended-note supersession that flags the existing claim
  - the arq job with an in-memory Redis
- **Contract test:** an Epic connector run against the fhir.epic.com sandbox, kept out of the default `uv run pytest`.
- **Extension:** Playwright tests of each adapter against synthetic DMÉ page snapshots.
- **Model switch:** `scripts/eval_extraction.py` on 2+ `consultations/` cases with the Canadian/local model and embeddings, compared with the current baseline.
- **End-to-end:** `make dev-fake` plus the worker; paste 3 notes, one of them with an unknown NAM. Check that they show in the inbox as `prêt` (2) and `à associer` (1), that the approve-all path creates claims, and that `npm run build` passes.

## 7. Working steps

Each step is a small, self-contained doc with tasks, files and a "done when". Order follows the roadmap.
Steps 04–05 are mostly non-code and run in the background from week 1.

| # | Step | Phase | Depends on |
|---|---|---|---|
| 01 | [Chat model provider abstraction](intake-step-01-chat-model-provider.md) | 1 | — |
| 02 | [Embedding model provider abstraction](intake-step-02-embedding-model-provider.md) | 1 | 01 |
| 03 | [Canadian/local model PoC and decision](intake-step-03-canadian-model-poc.md) | 1 | 01, 02 |
| 04 | [Partnerships kickoff](intake-step-04-partnerships-kickoff.md) (non-code) | 1 → | — |
| 05 | [Privacy and compliance package](intake-step-05-privacy-compliance-package.md) | 1 → 3 | 06 (purge job) |
| 06 | [`encounters` table and repository](intake-step-06-encounters-table.md) | 2 | — |
| 07 | [Intake core](intake-step-07-intake-core.md) | 2 | 06 |
| 08 | [Sample and manual connectors, ER shift paste](intake-step-08-sample-and-manual-connectors.md) | 2 | 07 |
| 09 | [Intake and encounter API routes](intake-step-09-intake-api-routes.md) | 2 | 07, 08 |
| 10 | [Background extraction worker (arq)](intake-step-10-background-extraction-worker.md) | 2 | 07, 09 |
| 11 | [Inbox UI](intake-step-11-inbox-ui.md) | 2 | 09, 10 |
| 11b | [Epic sandbox connector (demo, fake patients)](intake-step-11b-epic-sandbox-demo.md) | 2–3 | 07, 09, 11 |
| 12 | [Device tokens](intake-step-12-device-tokens.md) | 3 | 09 |
| 13 | [Browser extension and first DMÉ adapter](intake-step-13-browser-extension-first-adapter.md) | 3 | 12, 04 |
| 14 | [Extension side panel](intake-step-14-extension-side-panel.md) | 3 | 13 |
| 15 | [Scribe webhook channel](intake-step-15-scribe-webhook.md) | 4 | 07, 09, 04 |
| 16 | [Amended notes (versioning and claim re-review)](intake-step-16-amended-note-versioning.md) | 4 | 06, 07 |
| 17 | [Documentation nudges](intake-step-17-documentation-nudges.md) | 4 | 11 |
| 18 | [Billing deadline tracker](intake-step-18-billing-deadline-tracker.md) | 4 | 06, 11 |
| 19 | [Epic (DSN) production integration](intake-step-19-epic-smart-on-fhir-connector.md) | 5 | 11b, 16, 04 |
| 20 | [TELUS (Medesync) API connector](intake-step-20-telus-chr-connector.md) | 5 | 07, 10, 16, 04 |
| 21 | [Omnimed pre-billing hook](intake-step-21-omnimed-prebilling-hook.md) | 5 | 07, 09, 16, 04 |

## Open items to verify (not confirmed by research)
- TELUS CHR Enterprise API scope for Medesync clinics; Omnimed partner terms and launch-hook mechanics.
- Santé Québec's process for third-party SMART apps on the DSN, and whether GMF-U/CLSC family doctors chart in it.
- The current RAMQ billing deadline for omnipraticiens; whether the LRSSS applies to private GMFs.
- Market share per DMÉ among omnipraticiens (no public figure found).

## Sources
- MSSS DMÉ vendors: https://www.quebec.ca/sante/professionnels/programme-quebecois-adhesion-dossiers-medicaux-electroniques-en-specialite/liste-fournisseurs-dme
- Quebec AI transcription program: https://www.quebec.ca/sante/professionnels/programme-transcription-intelligence-artificielle
- DSN launch: https://www.lapresse.ca/actualites/sante/2026-05-09/dossier-sante-numerique/un-coup-d-envoi-marque-par-la-febrilite-et-des-pepins.php
- TELUS add-ons and CHR API: https://www.telus.com/en/health/health-professionals/clinics/emr-add-ons, https://help.inputhealth.com/en/articles/6483215-chr-enterprise-api, https://simplifier.net/teluspatientchart
- MYLE/CoeurWay: https://www.medfarsolutions.com/fr/scribe-ia-integree-vs-connectee-dme, https://www.medfarsolutions.com/fr/medfar-acquiert-coeurway/
- Xacte–Omnimed: https://www.xacte.net/blogue/integration-xacte-avec-dme-omnimed
- AutoScribe–Medesync: https://www.mutuohealth.com/post/autoscribe-est-maintenant-integre-au-dme-medesync
- Epic on FHIR: https://fhir.epic.com/Documentation
- Plume IA Chrome extension: https://chromewebstore.google.com/detail/plume-ia/gdiefbdmcclpfdnnbjbliofgpmegjkcb
