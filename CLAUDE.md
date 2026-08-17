# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a mandatory physician review step before
anything is submitted. **Scope: family doctors (omnipraticiens) only** — the RAMQ code
corpus is ingested from the *omnipraticien* remuneration manual specifically. Ingestion is
done by a different repo: ramq-ingestion wich produce a LanceDB.

## Architecture

1. `consultation_summary` task (`backend/app/summary/`) turns the raw transcript into
   structured, French-language clinical facts. It explicitly does *not* decide a billing
   code — administrative facts a code depends on (registration status, panel size, billing
   history) aren't derivable from a transcript.
2. `billing_codes` task (`backend/app/ramq_codes/`) takes the *rendered summary text*, not
   the raw transcript, and:
   - retrieves candidate *numbers* via `RAMQCodesRetriever` (`ramq_codes/retriever.py`), a
     llama_index `BaseRetriever` built on a `VectorStoreIndex` over the `code-embeddings`
     LanceDB table at `DB_PATH` (a `LanceDBVectorStore`, wired in `app/lancedb/factory.py`),
     embedded with Mistral's `mistral-embed`. `code-embeddings` node metadata carries only
     `number` (see ramq-ingestion's `src/embedding/code_node_builder.py`) — nothing else.
   - joins those numbers against the flat `codes` table (same `DB_PATH`) for the full
     candidate row (`description`, `when_to_use`, `rules`, `fees`, `confidence`; see
     ramq-ingestion's `src/embedding/code_table_schema.py`) — this join is `task.py`'s job,
     not the retriever's: `BillingCodesTask.build_prompt` calls `CodesData.get(numbers)`
     (`ramq_codes/codes_data.py`), which does a direct LanceDB query
     (`table.search().where("number IN (...)")`) via `CodeTable` (`app/lancedb/db.py`) and
     converts each raw row into this backend's own `Code` shape via `CodesRowConverter`
     (`app/lancedb/converter.py`). A candidate number with no matching `codes` row (stale
     index) is silently dropped rather than surfaced with missing data.
   - asks the model to pick only from those candidates, attaching a fee (from the
     candidate's own fee list, never invented) and a verbatim `supporting_quote` from the
     summary per code, for physician review. Empty output is correct/expected when nothing
     is clearly supported — never picks a "closest" candidate just to return something.
3. `ramq_chatbot` task (`backend/app/ramq_chatbot/`): a free-form, multi-turn chatbot for
   generic billing questions — not tied to any specific encounter/transcript, unlike
   `billing_codes`. Wired at `POST /query` (`app/main.py`). History is stateless: the
   client resends prior turns each request; nothing is persisted server-side.

**RAMQ data is a generated, external artifact.** The LanceDB tables at `DB_PATH`
(`code-embeddings` for retrieval, `codes` for full row data) are produced by a separate
sibling repo, `ramq-ingestion` (`~/Software/ramq-ingestion`) — this backend has no code
dependency on it, only on those tables' shapes.

**Frontend** (`frontend/`, React + TypeScript + Vite): a single-page transcript-in,
codes-out UI (`src/App.tsx`), typed API client in `src/api.ts`. `/api/*` proxies to the
backend per `vite.config.ts` — no CORS config, no hardcoded backend URL. Types in `api.ts`
must be kept in sync by hand with the backend's Pydantic response models (no codegen).

**`consultations/`** at repo root holds freeform, French-language synthetic clinical notes,
one per file — served as "simulated patients" (`GET /patients`, `GET /patients/{id}`, parsed
by `backend/app/sample_patients.py`) for demoing/testing without hand-typing a transcript.
`README.md` and `all_notes.md` in that directory are not patient files and are skipped.

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
