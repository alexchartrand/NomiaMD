# Step 01 — Chat model provider abstraction

**Phase:** 1 (weeks 1–4) · **Depends on:** — · **Unblocks:** 03
**Plan section:** §3 Data residency, §4 LLM provider abstraction

## Goal
Make the chat LLM swappable through configuration, so a Canadian-hosted, OpenAI-compatible
endpoint (vLLM/TGI) can replace the Mistral API without touching task code.

## Current state
- `backend/app/extraction/engine.py`'s `get_client(model)` builds a llama-index `MistralAI`
  client directly. `run_extraction` reads `response.raw["choices"][0].finish_reason` and
  `response.raw["model"]` (Mistral's response shape).
- `backend/app/ramq_chatbot/factory.py` builds its own `MistralAI` instance.
- `MISTRAL_ENDPOINT` (read by the llama-index client) points the app at
  `scripts/fake_llm_server.py` (`make dev-fake`).

## Tasks
- [ ] New package `backend/app/llm/`:
  - `chat.py`: `get_chat_llm(model) -> llama_index LLM`, cached per model. Selects the
    provider from `LLM_PROVIDER` (`mistral` | `openai_compatible`).
  - `mistral.py`: today's `MistralAI` construction (temperature 0, max_tokens 4096).
  - `openai_compatible.py`: llama-index `OpenAILike` against `LLM_ENDPOINT` + `LLM_API_KEY`,
    same determinism settings, `is_chat_model=True`.
  - `response.py`: `ChatResponseReader` that pulls `finish_reason`, the model name and the
    content out of either provider's raw response (one place for the shape differences).
- [ ] `Settings` (`backend/app/config.py`): `llm_provider`, `llm_endpoint`, `llm_api_key` as
  lazy properties, the same way `mistral_api_key` is read (keeps the `no_real_api_keys` safety net).
- [ ] `engine.py`: keep `get_client` as the name tests patch, but make it delegate to
  `get_chat_llm`. Use `ChatResponseReader` instead of indexing `response.raw` directly.
  Check how `OpenAILike` passes `response_format` (json_schema, strict).
- [ ] `ramq_chatbot/factory.py`: build its LLM through `get_chat_llm`.
- [ ] Make sure `scripts/fake_llm_server.py` answers both clients (the OpenAI and Mistral
  shapes are nearly identical). Update `Makefile` `dev-fake`, `.env.example`, and the docstrings
  in `try_extraction.py`/`eval_extraction.py` that mention `MISTRAL_ENDPOINT`.
- [ ] Add the deps with `uv add llama-index-llms-openai-like`.

## Files
`backend/app/llm/*` (new), `backend/app/extraction/engine.py`, `backend/app/ramq_chatbot/factory.py`,
`backend/app/config.py`, `backend/.env.example`, `Makefile`, `backend/scripts/fake_llm_server.py`.

## Done when
- `uv run pytest` passes unchanged (the tests still patch `app.extraction.engine.get_client`).
- New tests: provider selection by env; `ChatResponseReader` on a Mistral-shaped and an
  OpenAI-shaped raw response; an unknown provider fails at startup with a clear error.
- `make dev-fake` works with `LLM_PROVIDER=openai_compatible LLM_ENDPOINT=http://localhost:8080/v1`.

## Out of scope
Embeddings (step 02). Choosing the model and hosting (step 03).
