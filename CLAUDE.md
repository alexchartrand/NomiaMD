# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a mandatory physician review step before
anything is submitted. **Scope: family doctors (omnipraticiens) only** — the RAMQ code
corpus is ingested from the *omnipraticien* remuneration manual specifically. Ingestion is
done by a different repo: ramq-ingestion wich produce a LanceDB.

## Commands

From repo root:
```bash
make dev        # backend (:8000) + frontend (:5173)
make dev-fake   # same, but backend points at a fake local Mistral-compatible server
                # instead of burning real API calls (make fake-llm alone also works)
```

Backend (`cd backend`, venv at `.venv`):
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # fill in MISTRAL_API_KEY, DB_PATH
uvicorn app.main:app --reload

pytest                          # full suite, mocked model responses, no network/API key needed
pytest tests/test_pipeline.py   # single file
pytest tests/test_pipeline.py::test_name -v   # single test

python scripts/try_extraction.py    # runs the real pipeline against a sample transcript
python scripts/eval_extraction.py   # scores extraction against tests/fixtures/eval_billing_codes.jsonl
```

Frontend (`cd frontend`):
```bash
npm install
npm run dev      # proxies /api to localhost:8000, see vite.config.ts
npm run build    # tsc -b && vite build
```

## Architecture

1. `consultation_summary` task (`backend/app/summary/`) turns the raw transcript into
   structured, French-language clinical facts. It explicitly does *not* decide a billing
   code — administrative facts a code depends on (registration status, panel size, billing
   history) aren't derivable from a transcript.
2. `billing_codes` task (`backend/app/ramq_codes/`) takes the *rendered summary text*, not
   the raw transcript, and:
   - retrieves RAMQ candidates via `RAMQCodesRetriever` (`ramq_codes/retriever.py`), a
     llama_index `BaseRetriever` that embeds the query itself and does a direct LanceDB
     vector search (`table.search(...)`) over the `codes` table at `DB_PATH`, embedded with
     Mistral's `mistral-embed` — no `VectorStoreIndex` involved, since the table's columns
     are flat (`number`, `description`, `when_to_use`, `rules`, `fees`, `confidence`, `text`,
     `vector`; see ramq-ingestion's `src/embedding/code_table_schema.py`), not a llama_index
     metadata blob. Currently returns top-20 hits unconditionally — no relevance floor, no
     dedup (a prior `MIN_SIMILARITY` floor was dropped during an earlier retriever rewrite
     and hasn't been reinstated) — treat candidate narrowing as a known gap.
   - asks the model to pick only from those candidates, attaching a fee (from the
     candidate's own fee list, never invented) and a verbatim `supporting_quote` from the
     summary per code, for physician review. Empty output is correct/expected when nothing
     is clearly supported — never picks a "closest" candidate just to return something.
3. ramq_query: Used to answers generic questions about billing from a user. Will be wired in a later stage. 
It's only called by simple_query.py script.

**RAMQ data is a generated, external artifact.** The LanceDB `codes` table at `DB_PATH` is
produced by a separate sibling repo, `ramq-ingestion` (`~/Software/ramq-ingestion`) — this
backend has no code dependency on it.

**Frontend** (`frontend/`, React + TypeScript + Vite): a single-page transcript-in,
codes-out UI (`src/App.tsx`), typed API client in `src/api.ts`. `/api/*` proxies to the
backend per `vite.config.ts` — no CORS config, no hardcoded backend URL. Types in `api.ts`
must be kept in sync by hand with the backend's Pydantic response models (no codegen).

**`consultations/`** at repo root holds freeform, French-language synthetic clinical notes,
one per file — served as "simulated patients" (`GET /patients`, `GET /patients/{id}`, parsed
by `backend/app/sample_patients.py`) for demoing/testing without hand-typing a transcript.
`README.md` and `all_notes.md` in that directory are not patient files and are skipped.

## Working in this codebase
- Always use OOP, with best parctice principles.
- Code should always be modulable and buisiness logic should be split from implementation
- Tests always run against a stubbed keyword retriever and mocked model responses
  (`backend/tests/conftest.py`'s `small_reference_table`/`no_real_api_keys` fixtures,
  autouse) — no network, no API key, no real LanceDB needed. Never rely on
  `MISTRAL_API_KEY`/real retrieval being present in a test.
- Real-API scripts (`try_extraction.py`, `eval_extraction.py`) need `MISTRAL_API_KEY` and
  `DB_PATH`, or `MISTRAL_ENDPOINT` pointed at `scripts/fake_llm_server.py` (`make fake-llm`)
  to avoid spending real API calls.
