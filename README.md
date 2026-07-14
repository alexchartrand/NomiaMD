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
see `_meta` in that file for provenance and `backend/app/ramq/ingest/` for how it was
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
2. Asks the model (freeform JSON with the schema described in the prompt by default — see
   `NOMIAMD_STRUCTURED_OUTPUT` below — or grammar-constrained structured output for models
   capable of it) to pick from those candidates only, with a supporting quote per code for
   physician review.

Adding `prescriptions` or `consultation_notes` later: write a new class implementing
`ExtractionTask`, register it in `registry.py`, done.

## RAMQ data ingestion

`backend/app/ramq/reference_data.json` is generated, not hand-written — regenerate it via
`backend/scripts/ingest_ramq_manual.py` rather than editing it directly. The RAMQ manual
site blocks automated fetching (Cloudflare), so the source export has to be saved manually
(browser Save-As-HTML or print-to-PDF) into `backend/data/raw/` (gitignored — it's a large
derived artifact, not committed).

Two stages, with a human review pass in between (real regulatory text needs one):

```bash
# Stage 1: parse the export into a spreadsheet-friendly review CSV.
python scripts/ingest_ramq_manual.py extract --input data/raw/manuel.html --output data/raw/ramq_codes_raw.csv

# ... open the CSV, fix anything flagged needs_review=1 or otherwise wrong ...

# Stage 2: promote the reviewed CSV into reference_data.json.
python scripts/ingest_ramq_manual.py promote --input data/raw/ramq_codes_raw.csv \
    --output app/ramq/reference_data.json \
    --source-document "Manuel des médecins omnipraticiens — Rémunération à l'acte"
```

`backend/app/ramq/ingest/parse_html.py`'s docstring documents the real table shapes this
parser handles (standard fee rows, multi-price rows, majoration/surcharge rows, grouping
headers, continuation rows) and the heuristics used where the source markup is ambiguous
about row hierarchy — those heuristic resolutions are what `needs_review` flags. PDF export
isn't implemented yet (`parse_pdf.py` doesn't exist) — add it if a PDF source is needed.

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
