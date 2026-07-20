"""OpenAI-compatible embeddings client for the semantic retrieval layer (EmbeddingRetriever
in retrieval.py). Deliberately separate from extraction/engine.py's chat-completion client
— embeddings and the extraction LLM can be different providers/endpoints; today the LLM
talks to whatever NOMIAMD_BASE_URL points at, while embeddings use OPENAI_API_KEY/
OPENAI_BASE_URL. Cloud now, matching the same cloud-first stance already taken for the
extraction LLM itself (local/self-hosted embeddings are future work once real patient data
is in scope).

NOMIAMD_EMBEDDING_BASE_URL lets this point at a gateway (e.g. OpenRouter, https://openrouter.ai/api/v1)
instead of OpenAI directly — same client either way. Model IDs on a gateway are often
provider-prefixed (e.g. "openai/text-embedding-3-small"); set NOMIAMD_EMBEDDING_MODEL
accordingly.

Entirely optional: without NOMIAMD_EMBEDDING_API_KEY set, embeddings_enabled() is False and
RamqReferenceTable falls back to BM25-only retrieval, unchanged from before this module
existed.

Two calling patterns use embed_texts():
- Query-time embedding of a transcript against RAMQ's precomputed corpus vectors (see
  reference.py) — always passes `model=` explicitly, pinned to whatever embedding_model the
  precomputed corpus file recorded, so the query lands in the same vector space no matter
  what NOMIAMD_EMBEDDING_MODEL happens to be set to locally.
- Embedding a small ad-hoc table from scratch (e.g. in tests, or any future caller with no
  precomputed vectors) — relies on the NOMIAMD_EMBEDDING_MODEL default below.
"""

import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI

EMBEDDING_MODEL = os.environ.get("NOMIAMD_EMBEDDING_MODEL", "text-embedding-3-small")

# Reference-table text (code descriptions, rule text) changes only when the manual is
# re-ingested, not per request — caching by exact text content avoids re-embedding the
# whole ~5,000-item table (cost + latency) on every process start.
_CACHE_PATH = Path(__file__).parent / ".embeddings_cache.json"

# OpenAI's endpoint accepts large batches; some OpenAI-compatible gateways (e.g.
# OpenRouter) cap around 96 inputs per request for many embedding models — stay under
# that universally rather than branching on which endpoint is configured.
_BATCH_SIZE = 96


def embeddings_enabled() -> bool:
    return bool(os.environ.get("NOMIAMD_EMBEDDING_API_KEY"))


def _cache_key(model: str, text: str) -> str:
    # Namespaced by model: a cached vector for one embedding model is meaningless (and
    # dangerous to silently reuse) as a stand-in for another model's vector space.
    return hashlib.sha256(f"{model}:{text}".encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    return {}


def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Embeds a batch of texts, filling in only what's missing from the on-disk cache.

    `model` defaults to NOMIAMD_EMBEDDING_MODEL but callers that need a specific model (e.g.
    matching a precomputed corpus's embedding_model) should pass it explicitly.
    """
    model = model or EMBEDDING_MODEL
    cache = _load_cache()
    keys = [_cache_key(model, t) for t in texts]
    missing = [(i, t) for i, (t, k) in enumerate(zip(texts, keys)) if k not in cache]

    if missing:
        client = OpenAI(api_key=os.environ["NOMIAMD_EMBEDDING_API_KEY"], base_url=os.environ.get("NOMIAMD_EMBEDDING_BASE_URL"))
        for start in range(0, len(missing), _BATCH_SIZE):
            chunk = missing[start : start + _BATCH_SIZE]
            response = client.embeddings.create(model=model, input=[t for _, t in chunk])
            for (i, _), item in zip(chunk, response.data):
                cache[keys[i]] = item.embedding
        _CACHE_PATH.write_text(json.dumps(cache))

    return [cache[k] for k in keys]
