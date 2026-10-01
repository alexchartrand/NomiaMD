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
| `extraction/` | `POST /extract`: runs the pipeline (`pipeline.py`) and the shared LLM call (`engine.py`) |
| `summary/` | `consultation_summary` task — transcript → structured French clinical facts, no codes |
| `ramq_codes/` | `billing_codes` task — billing context, candidate retrieval, eligibility, code selection |
| `ramq_chatbot/` | `POST /query` — stateless RAMQ manual chatbot (hybrid search + reference expansion) |
| `tasks/` | `ExtractionTask` base, task registry, strict JSON schema generation |
| `lancedb/` | read side of the RAMQ LanceDB tables (generic, never imports a domain package) |
| `postgresdb/` | ORM models, sessions, one repository module per aggregate |
| `auth/` | login/sessions (`AuthService`) and dated physician practice facts (`ProfileService`) |
| `patients/` | global patient identity, search, per-physician roster, registration |
| `claims/`, `bills/` | saving reviewed codes as claims; grouping claims into bills (+ PDF) |
| `sample_patients/` | serves `consultations/` notes as simulated patients |

`app/bootstrap.py`'s `application_services()` is the single composition root (opens LanceDB
and Postgres, registers tasks), used by `main.py`'s lifespan and by the scripts.

Extraction flow: the physician picks a patient *first* (global search), then `POST /extract`
(requires `patient_id`) runs `consultation_summary` → resolves a `BillingContext`
(physician practice facts + patient age/vulnerability/registration) → `billing_codes`
(multi-query hybrid retrieval, eligibility-filtered, RRF-fused → LLM picks from candidates).
The physician reviews, then `POST /claims` saves from the stored extraction run.

Frontend (`frontend/src/`): pages under `pages/app/` routed by `AppRouter.tsx`, typed API
client per domain under `api/`. `/api/*` proxies to the backend (`vite.config.ts`).

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
  `documents-embeddings` (chatbot) is in the same `DB_PATH`.
- **Frontend types in `src/api/` are kept in sync with backend Pydantic models by hand.**

`consultations/` holds synthetic French notes (one per file, `**NAM :**` header);
`scripts/seed_db.py` seeds them as patients. `README.md`/`all_notes.md` there are skipped.

## Working in this codebase
- Always use OOP, with best parctice principles. A class should has only one task and do it well.
- Code should always be modulable and buisiness logic should be split from implementation
- Tests always run against a stubbed keyword retriever and mocked model responses
  (`backend/tests/conftest.py`'s `small_reference_table`/`no_real_api_keys` fixtures,
  autouse) — no network, no API key, no real LanceDB needed. Never rely on
  `MISTRAL_API_KEY`/real retrieval being present in a test.
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
