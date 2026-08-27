 # NomiaMD

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a physician review step before anything is
submitted. Built to be extensible: adding a new output type (prescriptions, consultation
notes) means adding one new task definition, not redesigning the pipeline.

**Scope: family doctors (omnipraticiens) only, for now.** The RAMQ code corpus is ingested
from the *omnipraticien* remuneration manual specifically — it does not cover specialist
billing codes (a different manual, different nomenclature). A specialist code table and
extractor are future work, not yet started; don't assume the RAMQ LanceDB `codes` table
(at `DB_PATH`) is usable for a specialist encounter.

## ⚠️ Before using real patient data

This is being built for a real clinic pilot. **Confirm with the clinic whether transcripts
may be sent to a third-party LLM API at all** (Quebec's Law 25 and the clinic's own privacy
policy govern this) before any real, non-synthetic PHI touches this system. Everything in
this repo has been developed and tested against synthetic data only.

Also: the RAMQ candidate corpus (the LanceDB `codes` table at `DB_PATH`) is ingested from
the real *Manuel des médecins omnipraticiens — Rémunération à l'acte* (see the
`ramq-ingestion` repo for how it was parsed). It's a curated subset (currently ~370 codes),
not the full ~4,000-code manual — treat candidate retrieval as covering common cases, not
exhaustive.

## Layout

```
backend/     FastAPI service — transcript ingestion, extraction pipeline, storage
frontend/    React app — paste a transcript, review suggested codes
```

`consultations/` at the repo root holds a set of freeform, French-language synthetic
clinical notes, one per file. The backend serves these as selectable "simulated patients"
(`GET /patients`, `GET /patients/{id}`) and the frontend's dropdown loads a transcript
straight into the textarea from there — useful for demoing the pipeline without typing or
pasting a transcript by hand. `backend/scripts/try_extraction.py` reads its sample
transcript from the same source.

## Pricing

Fees are back, sourced per-code from `ramq-ingestion`'s extraction (`Code.fees`: amount,
the situation it applies to, and any majoration) rather than the earlier structured
patient/physician eligibility table that was dropped for being mostly wrong. Each
`ExtractedCode` now carries a `fee` (`backend/app/ramq_codes/models.py`), which
the model selects from that candidate's fee list based on the consultation summary —
picking the one whose condition applies when a code has several, or leaving all sub-fields
null when no fee data exists or none could be determined. Like the codes themselves, this
is not a verified/authoritative pricing source — a physician must confirm the amount before
billing.

## How it's extensible

Every output type implements `ExtractionTask` (`backend/app/tasks/base.py`): a system
prompt, a JSON schema for structured extraction, and a parser into a typed Pydantic result.
`backend/app/extraction/engine.py` is the shared LLM call — it never changes when a
new task is added. `backend/app/tasks/registry.py` is where new tasks get wired in.

Today there's one task, `billing_codes` (`backend/app/ramq_codes/task.py`), which:
1. Narrows the RAMQ corpus down to a small candidate list for the transcript via semantic
   similarity (`backend/app/ramq_codes/retriever.py`, a direct LanceDB vector search over the
   `codes` table at `DB_PATH`, embedded with Mistral's `mistral-embed`) — this keeps the
   model choosing from a known list instead of relying on its own recall of RAMQ codes, and
   keeps the candidate set small enough to fit in the prompt regardless of corpus size.
   Currently returns the top 20 hits unconditionally — there's no relevance floor, so an
   unrelated transcript still gets 20 candidates back rather than an empty or short list; a
   prior `MIN_SIMILARITY` cosine-similarity floor (and per-code dedup) was dropped during an
   earlier retriever rewrite and hasn't been reinstated, and there's no test pinning this
   behavior — treat candidate narrowing as a known gap, not a finished feature. Requires
   `MISTRAL_API_KEY` and `DB_PATH`.
2. Asks the model for grammar-constrained (`strict: true`) JSON matching the task's schema,
   to pick from those candidates only, with a supporting quote per code for physician
   review.

Adding `prescriptions` or `consultation_notes` later: write a new class implementing
`ExtractionTask`, register it in `registry.py`, done.

## RAMQ data ingestion

The LanceDB `codes` table at `DB_PATH` is generated, not hand-written. Ingestion (raw RAMQ
manual export → per-code `number`/`description`/`when_to_use`/`rules`/`fees`/`confidence`
→ embedded into LanceDB) lives in its own repo, `ramq-ingestion`
(`~/Software/ramq-ingestion` — no remote host set up yet), decoupled on purpose: this
backend consumes the LanceDB directory as a plain data artifact, with no code dependency on
how it was produced. See that repo's README to regenerate it.

An earlier iteration ingested a separate `reference_data.section_b.json` table carrying
per-code fees and structured patient/physician eligibility conditions. Most of that data
turned out to be wrong, so it and everything that depended on it were removed; fees have
since come back in a different, per-code free-text-qualified shape (see "Pricing" above) —
there is still no structured eligibility tag beyond what's in each code's `rules` text.

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
deterministically, not for judging extraction quality.

## Running the backend

```bash
cd backend
uv sync --extra dev
cp .env.example .env   # fill in MISTRAL_API_KEY
uv run uvicorn app.main:app --reload
```

The extraction engine (`backend/app/extraction/engine.py`) talks to the Mistral API
directly via llama_index's `MistralAI` client — set `MISTRAL_API_KEY`, and the model name
is a constant (`MODEL`) at the top of that file. No API key handy, or want to avoid real
API calls? Set `MISTRAL_ENDPOINT=http://localhost:8080` and point it at
`backend/scripts/fake_llm_server.py` instead (`make fake-llm`, or see "Quick start"
above) — a dumb but deterministic stand-in for testing/debugging the pipeline without a
real model.

- `GET /health` — lists registered tasks
- `POST /extract` — `{"transcript": "...", "task": "billing_codes"}` → suggested codes

Tests run against a mocked model response (no local server needed):

```bash
uv run pytest
```

To try it against the real Mistral API once `MISTRAL_API_KEY` is configured,
`scripts/try_extraction.py` runs the pipeline against a sample transcript pulled from
`consultations/` (see "Layout" above) — **this hasn't been run yet in this
environment**, so treat it as untested until you run it once yourself:

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
