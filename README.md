 # NomiaMD

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a physician review step before anything is
submitted. Built to be extensible: adding a new output type (prescriptions, consultation
notes) means adding one new task definition, not redesigning the pipeline.

**Scope: family doctors (omnipraticiens) only, for now.** The RAMQ code table is ingested
from the *omnipraticien* remuneration manual specifically — it does not cover specialist
billing codes (a different manual, different nomenclature). A specialist code table and
extractor are future work, not yet started; don't assume `reference_data.json` is usable
for a specialist encounter.

## ⚠️ Before using real patient data

This is being built for a real clinic pilot. **Confirm with the clinic whether transcripts
may be sent to a third-party LLM API at all** (Quebec's Law 25 and the clinic's own privacy
policy govern this) before any real, non-synthetic PHI touches this system. Everything in
this repo has been developed and tested against synthetic data only.

Also: the RAMQ code reference table (`backend/app/ramq/reference_data.json`) is ingested
from the real *Manuel des médecins omnipraticiens — Rémunération à l'acte* (~4,000 codes —
see `_meta` in that file for provenance and the `ramq-ingestion` repo for how it was
parsed). A meaningful fraction of entries are flagged `needs_review: true` where the
automated parser was uncertain (see "RAMQ data ingestion" below) — treat those as lower
confidence until spot-checked.

## Layout

```
backend/     FastAPI service — transcript ingestion, extraction pipeline, storage
frontend/    React app — paste a transcript, review suggested codes
```

`ClaudeCodingTest/`, `synthea/`, `synthetic_data/`, and `output/` are pre-existing
scratch/reference material (a getting-started script, the Synthea synthetic patient
generator, and a third-party synthetic consultation-transcript dataset) — not part of the
application.

`notes_consultation_simulees.md` at the repo root is a set of freeform, French-language
synthetic clinical notes (one per `## NOTE <n>` section). The backend serves these as
selectable "simulated patients" (`GET /patients`, `GET /patients/{id}`) and the frontend's
dropdown loads a transcript straight into the textarea from there — useful for demoing the
pipeline without typing or pasting a transcript by hand. `backend/scripts/try_extraction.py`
reads its sample transcript from the same source. Set `SAMPLE_PATIENTS_PATH` to point at a
different file in the same format instead.

## Pricing

Each RAMQ code in the reference table (`backend/app/ramq/reference_data.json`) carries a
`fees` list, not a single flat price — most real codes are billed differently depending on
context (e.g. *en cabinet ou à domicile* vs. *en CLSC ou en GMF-U*), and both amounts are
kept rather than discarding one. `RamqCode.price_cad` is a convenience property returning
the first/default fee variant's price. When a code is extracted,
`backend/app/tasks/billing_codes.py` looks this up from the reference table and attaches it
to the result — **the model never generates a price**; its JSON schema doesn't even include
a price field. `BillingCodesResult` also carries a `total_price_cad` (sum across codes that
have a price on file). This is deliberate: a monetary figure should come from a known table,
not LLM recall.

Time-of-day/weekend surcharges exist as their own "majoration" codes (`unit: "majoration %"`,
a `percentage` instead of `price_cad` on their fee variant) rather than being modeled as
automatic multipliers applied to a base code — that composition (which base codes a given
majoration applies to, and picking the right fee variant for the encounter's setting) is
still an open design question, not yet resolved.

## How it's extensible

Every output type implements `ExtractionTask` (`backend/app/tasks/base.py`): a system
prompt, a JSON schema for structured extraction, and a parser into a typed Pydantic result.
`backend/app/extraction/engine.py` is the shared LLM call — it never changes when a
new task is added. `backend/app/tasks/registry.py` is where new tasks get wired in.

Today there's one task, `billing_codes` (`backend/app/tasks/billing_codes.py`), which:
1. Narrows the RAMQ reference table (~4,000 real codes) down to a small candidate list for
   the transcript via BM25 (`backend/app/ramq/reference.py`, `backend/app/ramq/retrieval.py`)
   — this keeps the model choosing from a known list instead of relying on its own recall of
   RAMQ codes, and keeps the candidate set small enough to fit in the prompt regardless of
   table size. Retrieval is wrapped behind a small `Retriever` protocol so BM25 (lexical,
   local-first, no extra infra) can later be swapped for embeddings-based semantic retrieval
   without touching callers, once there's a stronger/hosted model in the loop to pair it
   with.

   **⚠️ Known gap:** every entry in `reference_data.json` has an empty `keywords` field
   (ingestion stub, `build_reference.py`) — retrieval currently relies entirely on BM25
   over each code's terse manual description/category, with French stemming to bridge
   simple inflection (a transcript saying "plaie" now matches a code description saying
   "plaies"). It does **not** bridge lay/clinical vocabulary vs. the manual's formal
   terminology (e.g. "coupure"/"couteau" won't match "Réparation de plaies" unless the
   word "plaie" itself is also present). If a code you'd expect to see just isn't showing
   up as a candidate, check this before assuming it's a model problem — either populating
   `keywords` for the relevant entries or adding a synonym-expansion layer would be the
   fix, neither of which exists yet.
2. Asks the model (freeform JSON with the schema described in the prompt by default — see
   `NOMIAMD_STRUCTURED_OUTPUT` below — or grammar-constrained structured output for models
   capable of it) to pick from those candidates only, with a supporting quote per code for
   physician review.

Adding `prescriptions` or `consultation_notes` later: write a new class implementing
`ExtractionTask`, register it in `registry.py`, done.

## RAMQ data ingestion

`backend/app/ramq/reference_data.json` is generated, not hand-written. Ingestion (raw RAMQ
manual export → `reference_data.json`) lives in its own repo, `ramq-ingestion`
(`~/Software/ramq-ingestion` — no remote host set up yet), decoupled on purpose: this
backend consumes `reference_data.json` as a plain data file, with no code dependency on how
it was produced. To regenerate it: run the ingestion pipeline there (see that repo's README
for the extract → human-review → promote stages, and why the source has to be a
manually-saved export rather than scraped), then copy the result over this file:

```bash
cp ~/Software/ramq-ingestion/output/reference_data.json backend/app/ramq/reference_data.json
```

`reference_data.json` itself continues to be tracked in this repo's git history exactly as
before — only how it gets regenerated has moved out.

## Quick start

From the repository root, run:

```bash
make dev
```

This starts:
- the backend on http://localhost:8000
- the frontend on http://localhost:5173

No local model server? Run `make dev-fake` instead — it also starts
`backend/scripts/fake_llm_server.py`, a tiny OpenAI-compatible dev server that listens on
the same `http://localhost:8080/v1` LocalAI would (no `.env` changes needed) and picks a
fixed number of candidate codes back per request instead of doing real extraction. It's for
exercising the pipeline and frontend end-to-end deterministically, not for judging
extraction quality.

## Running the backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in NOMIAMD_BASE_URL (and NOMIAMD_MODEL) to point at LocalAI
uvicorn app.main:app --reload
```

The extraction engine (`backend/app/extraction/engine.py`) talks to any OpenAI-compatible
chat completions endpoint — set `NOMIAMD_BASE_URL` to your LocalAI instance's `/v1` URL and
`NOMIAMD_MODEL` to a model name configured there. No model server available? Point
`NOMIAMD_BASE_URL` at `backend/scripts/fake_llm_server.py` instead (`make fake-llm`, or see
"Quick start" above) — a dumb but deterministic stand-in for testing/debugging the pipeline
without a real model.

- `GET /health` — lists registered tasks
- `POST /extract` — `{"transcript": "...", "task": "billing_codes"}` → suggested codes

Tests run against a mocked model response (no local server needed):

```bash
pytest
```

To try it against a real local model once LocalAI is running and configured,
`scripts/try_extraction.py` runs the pipeline against a sample transcript pulled from
`synthetic_data/` — **this hasn't been run yet in this environment**, so treat it as
untested until you run it once yourself:

```bash
python scripts/try_extraction.py
```

Storage defaults to a local SQLite file (`nomiamd.db`); set `DATABASE_URL` to point at
Postgres for anything beyond local dev.

## Running the frontend

Verified: `npm install`, `npm run build` (type-checks + bundles clean), and `npm run dev`
proxying through to a live backend (`/api/health`, `/api/extract`) all work.

```bash
cd frontend
npm install
npm run dev
```

It expects the backend running on `localhost:8000` (proxied via `/api`, see
`vite.config.ts`).

## Mobile

No mobile app yet. Recommendation from initial planning: ship the responsive web app for
the pilot first, and only build a native app (React Native, sharing logic with the React
web frontend) if the pilot shows physicians need it.
