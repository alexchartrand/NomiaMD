# NomiaMD

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a physician review step before anything is
submitted. Around that core it also manages patients, saved claims and bills, and has a
free-form RAMQ billing chatbot. Built to be extensible: adding a new output type
(prescriptions, consultation notes) means adding one new task definition, not redesigning
the pipeline.

**Scope: family doctors (omnipraticiens) only, for now.** The RAMQ code corpus is ingested
from the *omnipraticien* remuneration manual specifically — it does not cover specialist
billing codes (a different manual, different nomenclature). A specialist code table and
extractor are future work, not yet started; don't assume the RAMQ LanceDB code tables (at
`DB_PATH`) are usable for a specialist encounter.

## ⚠️ Before using real patient data

This is being built for a real clinic pilot. **Confirm with the clinic whether transcripts
may be sent to a third-party LLM API at all** (Quebec's Law 25 and the clinic's own privacy
policy govern this) before any real, non-synthetic PHI touches this system. Everything in
this repo has been developed and tested against synthetic data only.

Also: the RAMQ candidate corpus is ingested from the real *Manuel des médecins
omnipraticiens — Rémunération à l'acte* by the separate `ramq-ingestion` repo (~4,200 codes
in the current revision). Like the codes themselves, nothing it produces — codes, fees,
eligibility bounds — is an authoritative source: a physician must confirm every suggestion
before billing.

## Layout

```
backend/        FastAPI service — auth, patients, extraction pipeline, claims/bills, chatbot
frontend/       React + TypeScript + Vite app
consultations/  synthetic French clinical notes ("simulated patients")
DEPLOY.md       runbook for shipping a new version to the production server
```

`consultations/` holds a set of freeform, French-language synthetic clinical notes, one per
file. The backend serves these as selectable "simulated patients" (`GET /sample-patients`,
`GET /sample-patients/{id}`) and the extraction page's "Patient simulé" dropdown loads a
transcript straight into the textarea from there — useful for demoing the pipeline without
typing or pasting a transcript by hand. `backend/scripts/seed_db.py` also seeds each note's
patient (by its `**NAM :**` header) as a real patient record, and
`backend/scripts/try_extraction.py` reads its sample transcript from the same source.

## How extraction works

The physician first picks the patient (a global NAM/name search), then pastes or loads the
transcript. `POST /extract` runs two tasks in sequence
(`backend/app/extraction/pipeline.py`):

1. `consultation_summary` (`backend/app/summary/`) turns the raw transcript into
   structured, French-language clinical facts. It doesn't decide a code.
2. `billing_codes` (`backend/app/ramq_codes/`):
   - Resolves a billing context: the physician's practice facts in effect on the encounter
     date (panel size, remuneration type) and the patient's age, vulnerability and
     registration (derived by matching the patient's family-doctor practice number against
     the physician's own).
   - Retrieves candidates with hybrid (vector + native French full-text) LanceDB search
     over the current `codes_<rev>` table, embedded with Mistral's `mistral-embed`. One
     query for the visit plus one per procedure/add-on the summary called out, each
     filtered by the code variants' typed eligibility bounds, then fused with reciprocal
     rank fusion. This keeps the model choosing from a known list instead of relying on its
     own recall of RAMQ codes. There's no relevance floor: an unrelated transcript still
     gets candidates back.
   - Asks the model for grammar-constrained (`strict: true`) JSON picking only from those
     candidates, each with a confidence, a verbatim supporting quote, and any eligibility
     axis the physician must confirm. Codes outside the candidate set are dropped.

## Pricing

The model never picks a fee. Each suggested code's fee list is resolved server-side, by
exact code number, from the candidate's own row in the LanceDB codes table (amount, role,
unit, context, place of service). When a code has several fees the physician picks one in
the review UI; saving a claim (`POST /claims`) snapshots the chosen fee onto the claim, so
regenerating the LanceDB data later never rewrites billing history. A fee counted in
`unités` (anesthesia base units) is displayed but never billed as a dollar amount.

## How it's extensible

Every output type implements `ExtractionTask` (`backend/app/tasks/base.py`): a system
prompt, a JSON schema for structured extraction, a parser into a typed Pydantic result, and
an optional per-task `model` override (default `mistral-small-latest`; `billing_codes` uses
`mistral-medium-latest`). `backend/app/extraction/engine.py` is the shared LLM call — it
never changes when a new task is added. `backend/app/tasks/registry.py` is where new tasks
get wired in.

Adding `prescriptions` or `consultation_notes` later: write a new class implementing
`ExtractionTask`, register it in `registry.py`, then call it from a pipeline/route.

## RAMQ data ingestion

The LanceDB directory at `DB_PATH` is generated, not hand-written. Ingestion (raw RAMQ
manual → per-code rows with description, rules, fees and typed eligibility bounds, plus the
manual's prose for the chatbot → embedded into LanceDB) lives in its own repo,
`ramq-ingestion` (`~/Software/ramq-ingestion` — no remote host set up yet), decoupled on
purpose: this backend consumes the LanceDB directory as a plain data artifact, with no code
dependency on how it was produced. See that repo's README to regenerate it.

Codes are versioned: one `codes_<rev>` table per manual revision, plus a `code_versions`
registry whose `is_current` row names the table to retrieve from. The backend re-reads that
registry on each lookup, so promoting a new revision takes effect without a restart, and it
refuses to start if no revision is current. The chatbot's `documents-embeddings` table lives
in the same directory.

## Quick start

From the repository root, run:

```bash
make dev
```

This starts:
- the backend on http://localhost:8000
- the frontend on http://localhost:5173

Don't want to spend real Mistral API calls? Run `make dev-fake` instead — it also starts
`backend/scripts/fake_llm_server.py`, a tiny dev server that speaks the same wire protocol
as the Mistral API, and picks a fixed number of candidate codes back per request instead of
doing real extraction. It's for exercising the pipeline and frontend end-to-end
deterministically, not for judging extraction quality. Embeddings for retrieval still come
from the real Mistral API.

There's no signup page. On a fresh database, seed a demo physician account (prompts for its
password) and the 25 simulated patients:

```bash
cd backend
uv run python scripts/seed_db.py
```

## Running the backend

```bash
cd backend
uv sync --extra dev
cp .env.example .env   # fill in MISTRAL_API_KEY, DB_PATH, JWT_SECRET_KEY; COOKIE_SECURE=false locally
uv run uvicorn app.main:app --reload
```

The extraction engine (`backend/app/extraction/engine.py`) and the chatbot get their chat
model from `backend/app/llm/`, which `LLM_PROVIDER` switches between the Mistral API
(`mistral`, default) and any OpenAI-compatible server such as vLLM/TGI (`openai_compatible`,
with `LLM_ENDPOINT` + `LLM_API_KEY`). No API key handy, or want to avoid real API calls? Set
`LLM_PROVIDER=openai_compatible LLM_ENDPOINT=http://localhost:8080/v1 LLM_API_KEY=fake` and
run `backend/scripts/fake_llm_server.py` (`make fake-llm`, or `make dev-fake` which does both).

Retrieval's query embeddings come from the same package: `EMBEDDING_PROVIDER` switches
between Mistral (`mistral`, default, `MISTRAL_EMBEDDING_MODEL`) and any server exposing
`/v1/embeddings` such as TEI/vLLM (`openai_compatible`, with `EMBEDDING_ENDPOINT` +
`EMBEDDING_MODEL`). The backend refuses to start when the query model's vector dimension
doesn't match the LanceDB tables', so a model switch needs the tables re-embedded in
`ramq-ingestion` first.

Main endpoints (all but `/health` and `/auth/login` need a logged-in session cookie):

- `GET /health` — lists registered tasks
- `/auth/*` — login/logout, current user and practice-facts profile, password change
- `/patients` — the caller's roster, global NAM/name search (`/patients/search?q=`), create
- `POST /extract` — `{"transcript": "...", "task": "billing_codes", "patient_id": 1}` →
  summary, suggested codes, and an `extraction_run_id`
- `/claims` — save reviewed codes from an extraction run as a claim, list, void a draft
- `/bills` — group claims into a bill, list, PDF export, void
- `POST /query` — RAMQ billing chatbot (stateless; the client resends prior turns)
- `/sample-patients` — the simulated patients from `consultations/`

New accounts are created with `scripts/create_user.py` (see `DEPLOY.md`).

Tests run against a mocked model response and a stubbed retriever — no API key, network or
real LanceDB needed:

```bash
uv run pytest
```

To try it against the real Mistral API once `MISTRAL_API_KEY` and `DB_PATH` are configured,
`scripts/try_extraction.py` runs the pipeline against a sample transcript pulled from
`consultations/` (see "Layout" above), and `scripts/eval_extraction.py` scores retrieval and
selection against a hand-labeled set (default `tests/fixtures/eval_billing_codes.jsonl`, still
a draft pending physician labeling):

```bash
uv run python scripts/try_extraction.py
```

Storage defaults to a local SQLite file (`backend/nomiamd.db`); set `DATABASE_URL` to point
at Postgres for anything beyond local dev. There are no migrations yet: tables are created
on startup if missing, so after a schema change delete the local DB and re-seed.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

It expects the backend running on `localhost:8000` (proxied via `/api`, see
`vite.config.ts`). `npm run build` type-checks and bundles.

## Deploying

Production runs the `docker-compose.yml` stack (Caddy → nginx frontend → backend → Postgres
+ Redis). See [DEPLOY.md](DEPLOY.md) for the release runbook.

## Mobile

No mobile app yet. Recommendation from initial planning: ship the responsive web app for
the pilot first, and only build a native app (React Native, sharing logic with the React
web frontend) if the pilot shows physicians need it.
