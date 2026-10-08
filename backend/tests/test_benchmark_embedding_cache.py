"""app/benchmark/embedding_cache.py: a repeated batch is served from disk and still reported,
with the original call's token count."""

from collections.abc import Sequence
from datetime import datetime, timezone

from app.benchmark.embedding_cache import CachedEmbeddingClient
from app.llm import IEmbeddingClient, LLMCallRecord, UsageRecorder, call_purpose, usage_scope


class _MeteredFake(IEmbeddingClient):
    """Records its own calls like the real SDK client does."""

    def __init__(self, recorder: UsageRecorder):
        self._recorder = recorder
        self.batches: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "mistral-embed"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        self._recorder.record(
            LLMCallRecord(
                kind="embedding", provider="mistral", model="mistral-embed", purpose=None,
                input_tokens=7 * len(texts), output_tokens=None, latency_ms=300.0,
                started_at=datetime.now(timezone.utc),
            )
        )
        return [[float(len(t))] for t in texts]


async def test_a_batch_is_embedded_once_then_served_from_disk(tmp_path):
    recorder = UsageRecorder()
    inner = _MeteredFake(recorder)
    cache = CachedEmbeddingClient(inner, tmp_path, recorder=recorder)

    first = await cache.embed(["a", "bb"])
    second = await cache.embed(["a", "bb"])

    assert first == second == [[1.0], [2.0]]
    assert inner.batches == [["a", "bb"]]
    assert (cache.misses, cache.hits) == (1, 1)


async def test_a_hit_is_reported_as_a_cached_call_with_the_original_tokens(tmp_path):
    recorder = UsageRecorder()
    cache = CachedEmbeddingClient(_MeteredFake(recorder), tmp_path, recorder=recorder)

    with usage_scope() as live:
        await cache.embed(["a", "bb"])
    with usage_scope() as cached, call_purpose("billing_codes.retrieval"):
        await cache.embed(["a", "bb"])

    [live_call] = live.records
    [cached_call] = cached.records
    assert (live_call.cached, live_call.input_tokens) == (False, 14)
    assert (cached_call.cached, cached_call.input_tokens, cached_call.purpose) == (True, 14, "billing_codes.retrieval")


async def test_a_different_batch_or_model_misses(tmp_path):
    recorder = UsageRecorder()
    inner = _MeteredFake(recorder)
    cache = CachedEmbeddingClient(inner, tmp_path, recorder=recorder)

    await cache.embed(["a"])
    await cache.embed(["a", "b"])

    assert inner.batches == [["a"], ["a", "b"]]
