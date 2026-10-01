# Step 02 — Embedding model provider abstraction

**Phase:** 1 (weeks 1–4) · **Depends on:** 01 (same config pattern) · **Unblocks:** 03
**Plan section:** §3 Data residency

## Goal
Query-time embeddings embed text derived from the transcript, so they carry PHI too. Make the
embedding model swappable and make the app refuse to start when the query model doesn't
match the vectors stored in LanceDB.

## Current state
- `backend/app/embedings.py`'s `get_embeding_model()` always returns `MistralAIEmbedding`.
- Used by `app/ramq_codes/factory.py` (codes retriever), `app/ramq_chatbot/factory.py`, and
  the two `ramq_*_smoke_test.py` scripts.
- The vectors in `codes_<rev>` and `documents-embeddings` were built by ramq-ingestion with a
  Mistral embedding model.

## Tasks
- [ ] Move to `backend/app/llm/embeddings.py` (keep `app/embedings.py` as a re-export, or
  update the 4 imports). Select the provider from `EMBEDDING_PROVIDER`
  (`mistral` | `openai_compatible`); `openai_compatible` uses `OpenAILikeEmbedding` against
  `EMBEDDING_ENDPOINT` (TEI and vLLM both expose `/v1/embeddings`).
- [ ] Dimension guard: at `application_services()` startup (`app/bootstrap.py`), embed a probe
  string and compare its length with the vector column dimension of the current codes table
  and the documents table. On mismatch, fail with a message naming both.
- [ ] Check whether ramq-ingestion records the embedding model name (in `code_versions` or table
  metadata). If it does, also compare the model name. If it doesn't, add an item to
  ramq-ingestion's BACKLOG.md (per the upstream-data feedback rule).
- [ ] `.env.example`: add `EMBEDDING_PROVIDER`, `EMBEDDING_ENDPOINT`, `EMBEDDING_MODEL`. Keep
  `MISTRAL_EMBEDDING_MODEL` as the mistral provider's setting.

## Files
`backend/app/llm/embeddings.py` (new), `backend/app/embedings.py`, `backend/app/bootstrap.py`,
`backend/app/config.py`, `backend/.env.example`.

## Done when
- Tests: provider selection; the dimension guard raises on a stub table with the wrong
  dimension; existing retriever tests are unchanged (they use the stubbed keyword retriever).
- The app starts against today's LanceDB with `EMBEDDING_PROVIDER=mistral`.

## Out of scope
Re-embedding the tables (ramq-ingestion, step 03).
