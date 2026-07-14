 # NomiaMD

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a physician review step before anything is
submitted. Built to be extensible: adding a new output type (prescriptions, consultation
notes) means adding one new task definition, not redesigning the pipeline.

## ⚠️ Before using real patient data

This is being built for a real clinic pilot. **Confirm with the clinic whether transcripts
may be sent to a third-party LLM API at all** (Quebec's Law 25 and the clinic's own privacy
policy govern this) before any real, non-synthetic PHI touches this system. Everything in
this repo has been developed and tested against synthetic data only.

Also: the RAMQ code reference table (`backend/app/ramq/reference_data.json`) currently
contains **placeholder codes and placeholder prices only** — see the `_warning` field in
that file. It must be replaced with the real RAMQ nomenclature and fee schedule before this
produces anything a physician should trust.

## Layout

```
backend/     FastAPI service — transcript ingestion, extraction pipeline, storage
frontend/    React app — paste a transcript, review suggested codes
```

`ClaudeCodingTest/`, `synthea/`, `synthetic_data/`, and `output/` are pre-existing
scratch/reference material (a getting-started script, the Synthea synthetic patient
generator, and a third-party synthetic consultation-transcript dataset) — not part of the
application, but useful as synthetic test input. `backend/scripts/try_extraction.py` reads
a sample transcript straight out of `synthetic_data/`.

`notes_consultation_simulees.md` at the repo root is a set of freeform, French-language
synthetic clinical notes (one per `## NOTE <n>` section). The backend serves these as
selectable "simulated patients" (`GET /patients`, `GET /patients/{id}`) and the frontend's
dropdown loads a transcript straight into the textarea from there — useful for demoing the
pipeline without typing or pasting a transcript by hand.

`train.jsonl` at the repo root (a 50-record set of synthetic South African English
consultations, same format/source as `synthetic_data/`) is still supported as an
alternate fixture set — set `SAMPLE_PATIENTS_PATH=../train.jsonl` to use it instead.
`backend/app/sample_patients.py` picks the parser from the file extension (`.md` vs.
`.jsonl`).

## Pricing

Each RAMQ code in the reference table (`backend/app/ramq/reference_data.json`) has a flat
`price_cad`. When a code is extracted, `backend/app/tasks/billing_codes.py` looks its price
up from the reference table and attaches it to the result — **the model never generates a
price**; its JSON schema doesn't even include a price field. `BillingCodesResult` also
carries a `total_price_cad` (sum across codes that have a price on file). This is
deliberate: a monetary figure should come from a known table, not LLM recall.

**Open design question, not yet resolved:** real RAMQ fees vary by modifiers — specialist
vs. GP, time of day/weekend, region, act complexity — none of which are modeled yet. The
schema is flat-price-per-code for now. Revisit this (`RamqCode.price_cad` in
`backend/app/ramq/reference.py`, and the `_pricing_note` in `reference_data.json`) once it's
clear which modifiers actually matter for this pilot, rather than guessing at the structure
now.

## How it's extensible

Every output type implements `ExtractionTask` (`backend/app/tasks/base.py`): a system
prompt, a JSON schema for structured extraction, and a parser into a typed Pydantic result.
`backend/app/extraction/engine.py` is the shared LLM call — it never changes when a
new task is added. `backend/app/tasks/registry.py` is where new tasks get wired in.

Today there's one task, `billing_codes` (`backend/app/tasks/billing_codes.py`), which:
1. Narrows the RAMQ reference table down to keyword-matched candidates for the transcript
   (`backend/app/ramq/reference.py`) — this keeps the model choosing from a known list
   instead of relying on its own recall of RAMQ codes, and keeps the candidate set small
   enough to fit in the prompt as the table grows.
2. Asks the model (structured outputs via `response_format`/`json_schema`) to pick from
   those candidates only, with a supporting quote per code for physician review.

Adding `prescriptions` or `consultation_notes` later: write a new class implementing
`ExtractionTask`, register it in `registry.py`, done.

## Quick start

From the repository root, run:

```bash
make dev
```

This starts:
- the backend on http://localhost:8000
- the frontend on http://localhost:5173

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
`NOMIAMD_MODEL` to a model name configured there.

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
