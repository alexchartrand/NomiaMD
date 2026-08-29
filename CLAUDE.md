# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Extracts RAMQ billing codes from clinical encounter transcripts (sourced from Epic or
ambient scribe tools like Plume AI), with a mandatory physician review step before
anything is submitted. **Scope: family doctors (omnipraticiens) only** — the RAMQ code
corpus is ingested from the *omnipraticien* remuneration manual specifically. Ingestion is
done by a different repo: ramq-ingestion wich produce a LanceDB.

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
2. `billing_codes` task (`backend/app/ramq_codes/`) takes the *rendered summary text*, not
   the raw transcript, and:
   - retrieves fully-hydrated candidates via `RAMQCodesRetriever`
     (`ramq_codes/retriever.py`), which calls `CodeRepository.hybrid_search`
     (`app/lancedb/repository.py`) — native LanceDB vector+FTS fusion (`MultiMatchQuery`
     over `number`/`libelle`/`description`/`lexical_terms`/`expansion_terms`) over the flat
     `codes` table at `DB_PATH` (an `AsyncTable`, held by `LanceDB`,
     `app/lancedb/database.py`), embedded with Mistral's `mistral-embed`. Unlike the old
     `code-embeddings` vector-store hit (metadata-only, just a bare `number`), a
     `hybrid_search` hit already carries the full row (`libelle`, `description`,
     `when_to_use`, `rules`, `fees`; see ramq-ingestion's
     `src/embedding/codes_embedding/code_table_schema.py`), so there's no separate
     hydrate-by-number join any more — `RAMQCodesRetriever.aretrieve` converts each hit
     straight into this backend's own `Code` shape via `CodesRowConverter`
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
   - asks the model to pick only from those candidates, attaching a fee (from the
     candidate's own fee list, never invented) and a verbatim `supporting_quote` from the
     summary per code, for physician review. Empty output is correct/expected when nothing
     is clearly supported — never picks a "closest" candidate just to return something.
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



**`app/patients/`** owns a physician's own patient roster (`Patient` in
`app/postgresdb/models.py`, CRUD at `/patients`) and NAM-based identification of that
roster from an extraction's identified patient (`PatientSuggestionService`, `app/patients/
nam.py`/`suggestion.py`) — matched by exact NAM only, never by name, since a NAM is unique
across every Quebec resident and a name-based near-miss risks billing the wrong person.
`Patient.is_deleted` makes patient deletion a soft delete: a deleted patient disappears from
the roster and its lookups, but any `claims` row referencing it keeps rendering the
patient's name, and the id is never left dangling.

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
pays for that dependency and only the profile screen needs it. `UserOut` flattens the two
halves back into one object, so the split is invisible to the frontend.

**`app/claims/`** turns a physician-confirmed `billing_codes` extraction into a persisted
claim — not an LLM task itself, just the save step downstream of it.
`ClaimService` hydrates each saved code's description/fee/quote from the extraction's own
stored result (never trusted from the request body) and snapshots them onto
`claim_codes`, since the LanceDB `codes` table they originally came from is
regenerated independently and re-deriving fees later would silently rewrite billing history.
Wired at `POST/GET/PATCH/DELETE /claims` (`app/main.py`).

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
`**Patient :**`/`**Dossier :**`/`**Date/heure :**`) so the NAM-matching path is exercisable
against real fixtures. `README.md` and `all_notes.md` in that directory are not patient
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
