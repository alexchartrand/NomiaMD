# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a mandatory physician review step before
anything is submitted. **Scope: family doctors (omnipraticiens) only** — the RAMQ code
corpus is ingested from the *omnipraticien* remuneration manual specifically. Ingestion is
done by a different repo: ramq-ingestion, which produces a LanceDB.

**PHI caution**: everything in this repo is developed/tested against synthetic data only
(`consultations/`). Confirm with the clinic whether transcripts may be sent to a
third-party LLM API at all (Quebec's Law 25 governs this) before real, non-synthetic
patient data ever touches this system.

## Commands

Backend (`backend/`, from that directory):
```bash
uv sync --extra dev              # install deps (see .env.example for required env vars)
uv run uvicorn app.main:app --reload   # run the API alone, http://localhost:8000
uv run pytest                    # full suite — mocked model + stubbed retriever, no network/API key/LanceDB needed
uv run pytest tests/test_patients.py            # one file
uv run pytest tests/test_patients.py::test_name -v   # one test
```
Real-API smoke scripts (`try_extraction.py`, `eval_extraction.py`) need `MISTRAL_API_KEY`
and `DB_PATH`, or `MISTRAL_ENDPOINT` pointed at `scripts/fake_llm_server.py` (`make
fake-llm`) to avoid spending real API calls. There's no lint/typecheck config on the
backend (no ruff/mypy in `pyproject.toml`).

Frontend (`frontend/`, from that directory):
```bash
npm install
npm run dev       # http://localhost:5173, proxies /api to the backend on :8000
npm run build     # tsc -b (type-check) + vite build — the closest thing to a typecheck/lint step; no eslint config exists
```

From the repo root, `make dev` runs backend + frontend together; `make dev-fake` also
starts `scripts/fake_llm_server.py` and points the backend at it, so nothing burns a real
Mistral API call.

## Git Guidelines

### Branch Naming
- Always use the format: `type/issue-description` (lowercase, kebab-case)
- Allowed types: feat, fix, chore, refactor, docs
- Example: `feat/api-migration`

### Commit Messages
- Follow Conventional Commits format: `<type>(<scope>): <short description>`
- Never commit directly to the `main` branch.
- Always write explicit, imperative descriptions (e.g., "add", not "added").


## Architecture

1. `consultation_summary` task (`backend/app/summary/`) turns the raw transcript into
   structured, French-language clinical facts. It explicitly does *not* decide a billing
   code — administrative facts a code depends on (registration status, panel size, billing
   history) aren't derivable from a transcript.
2. `billing_codes` task (`backend/app/ramq_codes/`) runs off a `BillingCodesInput`
   (`ramq_codes/task.py`) — the *structured* `consultation_summary` result, the raw
   transcript, and a resolved `BillingContext` (`ramq_codes/context.py`) — not the rendered
   summary text alone: any clinical detail the summarizer dropped would otherwise be an
   unrecoverable recall loss at selection time. The patient is no longer matched from the
   transcript after the fact — the physician picks one from a global search (`app/
   patients/`, see below) *before* calling `POST /extract`, which now requires a
   `patient_id` (`extraction/models.py`); `extraction/router.py` 404s upfront if it doesn't
   resolve. `app/extraction/pipeline.py`'s `run_billing_codes_pipeline` runs
   `consultation_summary` first, then a best-effort step that degrades silently (log and
   continue) rather than block extraction on failure: `BillingContextBuilder.build`
   (`ramq_codes/context_builder.py`, called with the required `patient_id` directly rather
   than a suggestion match) resolves the billing physician's own practice facts
   (`ProfileService.as_of`, not `.current` — the encounter date's panel size/remuneration
   type, not today's; falls back to `ProfileService.earliest` when the encounter predates the
   physician's first profile version, a deliberate best-effort trade-off flagged in
   BACKLOG.md for revalidation) and the chosen patient's registration/vulnerability/exact
   age, then `billing_codes` runs with all of that. `ConsultationSummaryResult` carries no
   patient-identity fields at all — those administrative facts reach `billing_codes`
   exclusively through `BillingContext`, never re-extracted from the transcript. Nothing
   links `SourceStep.tsx`'s "Patient simulé" transcript-loader dropdown to the real
   `PatientSearchSelect` picker below it — they're independent, and a mismatched pair is
   not caught at all (there is no transcript-vs-chosen-patient identity check any more).
   - `RAMQCodesRetriever` (`ramq_codes/retriever.py`) fans one encounter out into several
     retrieval queries via `SummaryQueryPlanner` (`ramq_codes/query_planner.py`) — one for
     the visit as a whole plus one per `procedures_performed`/`possible_billable_add_ons`
     entry, since a single blended query under-retrieves both a routine visit and a minor
     procedure documented in the same note — embeds each with Mistral's `mistral-embed`,
     runs `CodeRepository.hybrid_search` (`app/lancedb/repository.py`, native LanceDB
     vector+FTS fusion via `MultiMatchQuery` over `number`/`libelle`/`description`/
     `header_path`/`lexical_terms`/`expansion_terms`) over the flat `codes` table at
     `DB_PATH`, and fuses the per-query hit lists with `ReciprocalRankFuser`
     (`app/lancedb/fusion.py` — shared with `ramq_chatbot`, keyed on `Code.number` here vs.
     `DocumentRow.id` there). A `hybrid_search` hit already carries the full row (`libelle`,
     `description`, `header_path`, `when_to_use`, `rules`, `fees`; see ramq-ingestion's
     `src/embedding/codes_embedding/code_table_schema.py`), converted via `CodesRowConverter`
     (`app/lancedb/converter.py`). `app/lancedb/` mirrors `app/postgresdb/`'s
     `database.py`/`models.py`/`repository.py` split; unlike Postgres, LanceDB has no
     migration/session story, and its connection can only be opened once an event loop is
     running, so `LanceDB.open()` is called from `app/bootstrap.py`'s
     `application_services()` — the process's single composition root, used by
     `app/main.py`'s `lifespan` and by the real-API scripts. `CodeRepository.
     list_by_numbers`/`get_by_number` (a genuine by-key lookup, not retrieval) still exist
     for `ramq_chatbot`'s `ReferenceExpander`, which resolves RAMQ code numbers referenced
     in manual prose via `CodesData` (`ramq_codes/codes_data.py`) — a candidate number with
     no matching `codes` row there is silently dropped rather than surfaced with missing
     data.
   - `CodeFamilySelector` (`ramq_codes/family.py`) then collapses near-duplicate variants
     that share a `header_path` (the manual's own taxonomy path — most of the `codes` table
     is family variants differing only on panel size, patient vulnerability, registration
     status, or an age threshold) down to whichever variant `BillingContext` actually
     supports, dropping the rest; an axis neither the physician's profile nor the chosen
     patient could resolve leaves every variant in place and gets surfaced back to
     `BillingCodesTask`'s prompt as something the physician must confirm.
   - `BillingCodesTask` (`model = "mistral-medium-latest"`, stronger than
     `consultation_summary`'s default — see `app/tasks/base.py`'s per-task
     `ExtractionTask.model` and `app/extraction/engine.py`'s per-model client cache, since
     picking among near-identical tariff variants is harder than structural extraction) asks
     the model to pick only from those candidates, recall-first (a plausible candidate is
     included rather than dropped — mandatory physician review is the backstop, not the
     model's certainty), a `confidence` bucket (`high`/`medium`/`low`), a verbatim
     `supporting_quote` from the summary or transcript, and a `needs_confirmation` list
     naming any axis `CodeFamilySelector` couldn't resolve. Empty output is correct/expected
     when nothing is clearly supported — never picks a "closest" candidate just to return
     something. `BillingCodesTask.parse` also cross-checks every returned code against the
     candidate set `build_prompt` actually offered (`PreparedPrompt.candidate_numbers`,
     `app/tasks/base.py`), dropping and flagging anything the model invented outside it. The
     model never picks a fee — `ExtractedCode.fees` is excluded from the LLM-facing schema
     entirely (`json_schema_extra={"server_only": True}`, honored by `app/tasks/schema.py`'s
     `to_strict_schema`) and instead resolved after the LLM call, by exact code number
     (`BillingCodesTask.resolve_fees`, called from `app/extraction/pipeline.py`) straight off
     the candidate's real fee list — the physician picks among several variants in the review
     UI when a code has more than one; `POST /claims` (`app/claims/models.py`'s
     `SelectedCode.fee_index`) carries that choice back to `ClaimService`, which validates it
     against the same list before snapshotting it onto `claim_codes`.
3. `ramq_chatbot` task (`backend/app/ramq_chatbot/`): a free-form, multi-turn chatbot for
   generic billing questions — not tied to any specific encounter/transcript, unlike
   `billing_codes`. Wired at `POST /query` (`app/main.py`). History is stateless: the
   client resends prior turns each request; nothing is persisted server-side.
   `RAMQManualRetriever` fans one user query out into several via `LLMQueryGenerator`
   (`query_generator.py`), runs each through `DocumentRepository.hybrid_search`
   (`app/lancedb/repository.py`) — native LanceDB vector+FTS fusion over the flat
   `documents-embeddings` table, in the same `DB_PATH` directory as `codes` (one
   `AsyncConnection`, opened by `LanceDB.open()`) — then RRF-fuses the per-query hit lists
   across queries (`fusion.py`; LanceDB's own hybrid search already fuses vector+FTS
   *within* one query). `ReferenceExpander` (`reference_expansion.py`) pulls in one hop of
   `section_references`/`code_references` the hits' own prose points at, same convention as
   `billing_codes`' fee data: never invented, always joined from the table. Everything here
   is async-only — `IDocumentRepository` has no sync query path.



**`app/patients/`** — `Patient` (`app/postgresdb/models.py`) is a single global identity per
real person, unique by NAM across *all* physicians (a partial unique index scoped to
`deleted_at IS NULL`), not a per-physician roster row: any physician may look up or bill any
known patient. `PhysicianPatient` (`physician_patients`) is a separate, optional "my
patients" join table (`physician_id`, `patient_id`, `notes`) with no registration flag on
it — registration is derived, not stored. Routes split accordingly (`patients/router.py`):
`GET /patients` lists the caller's own roster; `GET /patients/search?q=` is a NAM/name
typeahead over *every* patient in the system (`PatientRepository.search`), powering
`PatientSearchSelect.tsx` (used both in extraction's source step and to add an existing
patient to one's roster from `PatientsPage.tsx`); `POST /patients` creates a new global
identity; `PATCH /patients/{id}` edits that shared record and is admin-only, since any
physician editing another physician's patient has no ownership check left to gate it; roster
membership itself is `POST/PATCH/DELETE /patients/roster...`. There is no endpoint that
deletes a global `Patient` — `deleted_at` is read everywhere (soft-delete semantics: gone
from search/roster, but a `claims` row referencing it keeps rendering the patient's name)
but nothing currently writes it.

`resolve_registration` (`app/patients/registration.py`) is the single shared definition of
"registered": an exact match between the patient's stored `family_doctor_practice_number`
and the physician's own `User.practice_number` (`app/auth/`, see below), returning `None`
(never a guess) when either side has no number on file — used identically by the API's
`is_registered_with_current_physician` and by `BillingContextBuilder`.

**`app/auth/`** splits authentication from the physician's practice facts.
`AuthService` owns credentials/tokens/sessions against `users`; `ProfileService`
(`auth/profile.py`) owns `physician_profiles`, an append-only table keyed by
`(user_id, effective_from)`. `physician_type`/`remuneration_type`/`number_of_patients`
live there rather than as columns on `users` because they decide which RAMQ codes a
physician may legally bill and they change over a career — read them with
`PhysicianProfileRepository.get_effective_on(user_id, date)` so a past claim or invoice is
interpreted under the values in effect on its own service date, never today's (same
reasoning as `ClaimCode`'s fee snapshot). `get_current` is that call with today's date.
`get_current_user` deliberately does *not* load a profile: every authenticated request
pays for that dependency and only the profile screen needs it. `User.practice_number`
(`postgresdb/models.py`) is the one practice fact that stays a plain column on `users`
rather than moving into the profile table — a RAMQ practice number essentially never
changes over a career, and it's exactly the value `resolve_registration` (see
`app/patients/` above) compares against a patient's stored `family_doctor_practice_number`
to derive registration. `UserOut` flattens the two halves back into one object, so the
split is invisible to the frontend.

**`app/claims/`** turns a physician-confirmed `billing_codes` extraction into a persisted
claim — not an LLM task itself, just the save step downstream of it.
`ClaimService` hydrates each saved code's description/fee/quote from the extraction's own
stored result (never trusted from the request body) and snapshots them onto
`claim_codes`, since the LanceDB `codes` table they originally came from is
regenerated independently and re-deriving fees later would silently rewrite billing history.
A claim's patient is looked up globally (`PatientRepository.get`), not against the billing
physician's own roster — any physician may bill any known patient now that `Patient` isn't
roster-scoped (see `app/patients/` above). Wired at `POST/GET/PATCH/DELETE /claims`
(`app/main.py`).

**RAMQ data is a generated, external artifact.** The LanceDB tables at `DB_PATH` (`codes`
for `billing_codes`, `documents-embeddings` for `ramq_chatbot` — one directory, both flat
tables carrying their own row data and embedding vector) are produced by a separate sibling
repo, `ramq-ingestion` (`~/Software/ramq-ingestion`) — this backend has no code dependency
on it, only on those tables' shapes.

**Frontend** (`frontend/`, React + TypeScript + Vite): a router (`src/AppRouter.tsx`) over
`src/pages/app/*` — extraction (a 3-step source/transcript/review-and-bill flow), patients,
facturation, chat, profile — with a typed API client in `src/api.ts`. `/api/*` proxies to
the backend per `vite.config.ts` — no CORS config, no hardcoded backend URL. Types in
`api.ts` must be kept in sync by hand with the backend's Pydantic response models (no
codegen).

**`consultations/`** at repo root holds freeform, French-language synthetic clinical notes,
one per file — served as "simulated patients" (`GET /sample-patients`, `GET
/sample-patients/{id}`, parsed by `backend/app/sample_patients/service.py`) for demoing/testing
without hand-typing a transcript. Every note's header carries a `**NAM :**` line (alongside
`**Patient :**`/`**Dossier :**`/`**Date/heure :**`); `scripts/seed_db.py` seeds each note as
a matching global `Patient` row so the search/registration paths have something real to find
in a freshly-seeded dev DB. `README.md` and `all_notes.md` in that directory are not patient
files and are skipped.

## Working in this codebase
- Always use OOP, with best parctice principles. A class should has only one task and do it well.
- Code should always be modulable and buisiness logic should be split from implementation
- Tests always run against a stubbed keyword retriever and mocked model responses
  (`backend/tests/conftest.py`'s `small_reference_table`/`no_real_api_keys` fixtures,
  autouse) — no network, no API key, no real LanceDB needed. Never rely on
  `MISTRAL_API_KEY`/real retrieval being present in a test.
- Real-API scripts (`try_extraction.py`, `eval_extraction.py`) need `MISTRAL_API_KEY` and
  `DB_PATH`, or `MISTRAL_ENDPOINT` pointed at `scripts/fake_llm_server.py` (`make fake-llm`)
  to avoid spending real API calls.
