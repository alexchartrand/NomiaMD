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
uv sync --extra dev              # install deps (see the repo-root .env.example for required env vars)
uv run uvicorn app.main:app --reload   # run the API alone, http://localhost:8000
uv run pytest                    # full suite — mocked model + stubbed retriever, no network/API key/LanceDB needed
uv run pytest tests/test_patients.py            # one file
uv run pytest tests/test_patients.py::test_name -v   # one test
uv run pytest -m epic_sandbox    # opt-in contract test against the live Epic sandbox (EPIC_SANDBOX_* set)
```
Benchmark (`scripts/benchmark.py`, `make bench ARGS=...` from the root): stores each labeled
note's summary, retrieval result and selected codes, with every call's tokens and latency, under
`backend/benchmarks/runs/<name>/` (gitignored; `promote` copies one to the committed
`benchmarks/baselines/`):
```bash
uv run python scripts/benchmark.py run --name mistral-base               # summary + retrieval, all 58 notes
uv run python scripts/benchmark.py run --name t --stages retrieval --query-source transcript   # control run
uv run python scripts/benchmark.py sweep --summaries-from mistral-base --similarity-top-k 20,30 --fused-top-k 40,60
uv run python scripts/benchmark.py run --name sel --stages selection --candidates-from mistral-base --selection-model M   # billing_codes on stored candidates
uv run python scripts/benchmark.py report <run> --baseline mistral-base  # metrics.json + report.md
```
The real-API smoke script (`try_extraction.py`) needs `LLM_API_KEY`,
`EMBEDDING_API_KEY` and `DB_PATH`; set `LLM_PROVIDER=openai_compatible LLM_ENDPOINT=http://localhost:8080/v1
LLM_API_KEY=fake` to point chat calls at `scripts/fake_llm_server.py` (`make fake-llm`)
instead of spending real API calls. There's no lint/typecheck config on the
backend (no ruff/mypy in `pyproject.toml`).

Frontend (`frontend/`, from that directory):
```bash
npm install
npm run dev       # http://localhost:5173, proxies /api to the backend on :8000
npm test          # vitest (jsdom + msw): no network or backend needed
npm run e2e       # Playwright journeys against a throwaway backend + the fake LLM (needs the root .env's Mistral key and DB_PATH; not run in CI)
npm run build     # tsc -b (type-check) + vite build — the closest thing to a typecheck/lint step; no eslint config exists
```

From the repo root, `make dev` runs backend + frontend together; `make dev-fake` also
starts `scripts/fake_llm_server.py` and points the backend's chat calls at it (retrieval
embeddings still hit the real Mistral API).

## Git Guidelines

### Branch Naming
- Always use the format: `type/issue-description` (lowercase, kebab-case)
- Allowed types: feat, fix, chore, refactor, docs
- Example: `feat/api-migration`

### Commit Messages
- Follow Conventional Commits format: `<type>(<scope>): <short description>`
- Never commit directly to the `master` branch.
- Always write explicit, imperative descriptions (e.g., "add", not "added").


## Architecture

Backend modules (`backend/app/`):

| Module | Role |
|---|---|
| `llm/` | chat and embedding clients (`IChatClient`/`IEmbeddingClient`, one `openai`-SDK adapter in `openai_client.py` — no llama-index), provider selection (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`: `mistral` \| `openai_compatible`), per-call metering (`usage.py`: tokens in/out + latency of every call, logged as `llm_call`, collected by `usage_scope()`, tagged by `call_purpose()`), startup embedding-dimension guard |
| `intake/` | where notes come from: connectors (sample, paste/upload + ER-shift splitter, Epic FHIR — `connectors/epic_fhir/`, sandbox demo behind `EPIC_SANDBOX_ENABLED`) → `IntakeService.receive(SourceNote)` — per-source normalizers (+ date order), NAM-only patient resolution, dedup, `ExtractionQueue`; derived encounter status (`status.py`), `POST /intake/notes`/`/intake/upload`. Never imports `ramq_codes` |
| `encounters/` | the inbox: `/encounters` (list over a service-date range, with derived status + `all_clean`, detail with latest run, manual patient pick, on-demand extract, "doublon possible" flags derived over the listed encounters + the physician's confirm/dismiss); wires `IntakeService` to the extraction pipeline |
| `dashboard/` | `GET /dashboard` — the landing page's read-only summary over the inbox's derived rows: to-do counts, unbilled work near RAMQ's 90-day billing deadline (`deadline.py`), draft/billed totals, weekly activity, latest encounters. Today comes from `get_clock` |
| `extraction/` | `POST /extract`: runs the pipeline (`pipeline.py`) and the shared LLM call (`engine.py`) |
| `summary/` | `consultation_summary` task — transcript → structured French clinical facts, no codes |
| `ramq_codes/` | `billing_codes` task — billing context, candidate retrieval, eligibility, code selection |
| `code_catalog/` | hand code search/lookup, no LLM and no embedding: `GET /codes/search` (digits = number prefix, else French FTS; empty = the physician's most billed codes; with `patient_id`, eligibility-filtered like retrieval + per-code `needs_confirmation`), `GET /codes/{number}`; `registry.py` holds the process's `ICodeCatalogRepository` (set by `application_services()`), which `claims/` reads hand-picked codes through |
| `benchmark/` | stage-by-stage benchmark over the labeled `consultations/` notes, never imported by the app: `EvalSetLoader` (fixture → cases), `SummaryStage`/`RetrievalStage`/`SelectionStage` (one record per note, calls metered; selection runs the real `BillingCodesTask` over a `FrozenCandidatesRetriever` replaying a stored retrieval, so `--candidates-from` cross-wires models), query sources (`summary` \| `transcript` \| `summary+transcript`), `RunStore` (`benchmarks/runs/`), `RetrievalScorer` (exact / family_only / ineligible / not_in_table / not_retrieved) and `SelectionScorer` (retained / possible / offered_not_selected / not_offered: precision on the retained codes, overall recall on both tiers; wrong variants, clean negatives), both scored at report time against the current labels, `RunAggregator`, `RunComparator`/`SelectionComparator`, `MarkdownReport`; `commands.py` wires them (opens LanceDB itself, so a non-current `--codes-table` can be benchmarked) |
| `ramq_chatbot/` | `POST /query` — stateless RAMQ manual chatbot (hybrid search + reference expansion) |
| `tasks/` | `ExtractionTask` base, task registry, strict JSON schema generation |
| `lancedb/` | read side of the RAMQ LanceDB tables (generic, never imports a domain package) |
| `postgresdb/` | ORM models, sessions, one repository module per aggregate |
| `auth/` | login/sessions (`AuthService`) and dated physician practice facts (`ProfileService`) |
| `patients/` | global patient identity, search, per-physician roster, registration |
| `claims/`, `bills/` | saving reviewed codes as claims — the run's suggestions plus codes added from the search (`ClaimCode.origin`), or a claim with no encounter at all (`POST/PUT /claims/manual`, `source_system="manual"`, no duplicate guard); grouping claims into bills (+ PDF) |
| `jwks/` | public `GET /.well-known/jwks.json`: the public keys committed in `jwks/public_keys/` (loaded at startup), what Epic's JWK Set URL points at; `kid` = RFC 7638 thumbprint, which the Epic signer derives from its private key |
| `contact/` | public `POST /contact` (no login): the site's contact form → `contact_requests`, best-effort email via SMTP (`LogContactNotifier` when unset), honeypot + 5/hour limit |
| `sample_patients/` | serves `consultations/` notes as simulated patients |

`app/bootstrap.py`'s `application_services()` is the single composition root (opens LanceDB
and Postgres, registers tasks), used by `main.py`'s lifespan and by the scripts.

Extraction flow: the physician picks a patient *first* (global search), then `POST /extract`
(requires `patient_id`) stores the note as an `Encounter` (the retention purge target; runs
cascade from it) and runs `consultation_summary` → resolves a `BillingContext`
(physician practice facts + patient age/vulnerability/registration) → `billing_codes`
(multi-query hybrid retrieval: a visit query rendered from the encounter's form only and scoped to the
manual's visit section, the full summary, one per procedure/add-on; eligibility-filtered, RRF-fused with every
visit hit kept, small code families completed → LLM picks from candidates: a short `analysis`, then the codes it is sure of
(`codes`, stored `retained`: preselected in the review, what inbox approve-all bills) and `other_possible_codes`).
The physician reviews (and may add codes from the code search), then `POST /claims` saves from
the stored extraction run. Billing without an encounter (`/app/facturer`) skips all of it:
patient + date + hand-picked codes → `POST /claims/manual`.

Frontend (`frontend/src/`): pages under `pages/app/` routed by `AppRouter.tsx`, typed API
client per domain under `api/`. The public site (`/`, `/prix`, `/contact`, `/securite`,
`/confidentialite`) shares `pages/site/SiteLayout.tsx`; landing sections live in
`pages/landing/`, and contact details, prices and plans in `src/site/` (`config.ts`,
`pricing.ts`) — the one place to edit them. The landing page after login is the dashboard (`/app`, `pages/app/DashboardPage/`: tasks, KPIs, activity chart, latest encounters, and the RAMQ assistant beside them — one conversation shared with `/app/chat` through `chat/RamqChatProvider.tsx`, mounted in `AppLayout`). The inbox is `/app/inbox`; a row opens
`/app/inbox/:encounterId` (note + code review, `pages/app/review/`); notes are added by hand
on `/app/ajouter`. `/app/facturer` bills without an encounter (and edits such a draft at
`/app/facturer/:claimId`); `/app/codes` is the RAMQ code reference. `/api/*` proxies to the backend (`vite.config.ts`).

### Invariants — don't break these

- **The model never decides administrative facts or fees.** Registration, vulnerability, age
  and panel size come from the DB via `BillingContext`, never from the transcript. Fees are
  resolved server-side by code number after the LLM call (`server_only` schema fields).
- **Eligibility is deterministic.** Code variants carry typed bounds; contradicted variants
  are filtered in the LanceDB `WHERE`. Axes the context can't resolve are surfaced as
  `needs_confirmation`, never guessed. An *assumed* panel size (`PhysicianContext.is_assumed`)
  never filters — read `confirmed_panel_size`.
- **The model only picks from offered candidates** — anything else is dropped. Empty output
  is a valid answer.
- **Codes the physician adds by hand are eligibility-checked server-side** against the current
  codes table with the claim's own `BillingContext` (`claims/catalog.py`) — the search UI hiding
  them isn't the guard. Their description and fees are snapshotted from that table by number,
  never from the request body; a code the run offered is snapshotted from the run instead.
- **Practice facts are dated.** Read them with `ProfileService.as_of(user, service_date)`,
  not today's values. "Today" comes from the injected `Clock` (America/Montreal), never
  `date.today()`.
- **Registration is derived, never stored**: `resolve_registration` matches the patient's
  `family_doctor_practice_number` to `User.practice_number`; `None` when either is missing.
- **Claims snapshot everything** (description, fee, billing context) at save time, hydrated
  from the stored extraction run, never from the request body — the LanceDB tables are
  regenerated independently. A claim's patient always comes from its extraction run.
- **Nothing is hard-deleted.** Claims/bills are voided (`voided_at`); claim status is derived
  (`soumis` iff `bill_id` set). Patients are global, unique by canonical NAM.
- **RAMQ data is an external artifact** from `ramq-ingestion` (`~/Software/ramq-ingestion`),
  no code dependency. Codes live in versioned `codes_<rev>` tables; `code_versions`'
  `is_current` row picks the one to use (re-read per call; no current row = startup error).
  `documents-embeddings` (chatbot) is in the same `DB_PATH`. The query embedding model must
  match the one that built their vectors; `application_services()` refuses to start on a
  dimension mismatch (`app/llm/embedding_guard.py`).
- **Frontend types in `src/api/` are kept in sync with backend Pydantic models by hand.**

`consultations/` holds synthetic French notes (one per file, `**NAM :**` header);
`scripts/seed_db.py` seeds them as patients. `README.md`/`all_notes.md` there are skipped.

## Working in this codebase
- Always use OOP, with best parctice principles. A class should has only one task and do it well.
- Code should always be modulable and buisiness logic should be split from implementation
- Tests always run against a stubbed keyword retriever and mocked model responses
  (`backend/tests/conftest.py`'s `small_reference_table`/`no_real_api_keys` fixtures,
  autouse) — no network, no API key, no real LanceDB needed. Never rely on
  an API key/real retrieval being present in a test.
- Transactions: repositories (`app/postgresdb/repositories/`) take an `AsyncSession` and only
  `flush()`, never commit. Whoever opens the session owns the outcome: `session_scope()`
  commits on normal exit, rolls back on exception. Routes depend on `DbSession` (one session
  per request). Exceptions: `get_current_user` and `POST /extract` open short
  `session_scope()`s so no pooled connection is held across LLM calls. Nothing is built at
  import time — `PostgresDB.open()`/`LanceDB.open()` run from `app/bootstrap.py`.
- No Alembic until the first release: `create_all` only creates missing tables, so a schema
  change means deleting the local DB (`backend/nomiamd.db`, or the Postgres volume) and
  re-seeding. SQLite's `CURRENT_TIMESTAMP` is second-precision, so any `ORDER BY` on a
  timestamp needs an `id` tie-breaker. Postgres-only DDL uses `.ddl_if(dialect="postgresql")`,
  with a SQLite equivalent where one exists.
- SQLite enforces foreign keys (`PRAGMA foreign_keys=ON`, `app/postgresdb/database.py`), in
  dev and in tests. A test that hands a route or repository a fixed-id in-memory `User` must
  seed its row first with `tests/db_helpers.py`'s `ensure_user_row` (conftest's default
  `User(id=1)` already does). Repository-level tests use conftest's `db_session` (rolled
  back at teardown); tests that seed data and then call the API seed through
  `session_scope()` so the app's own sessions can see it.
