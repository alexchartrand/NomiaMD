"""A disk cache in front of the real embedding client, so a retrieval sweep over stored
summaries embeds each query batch once, ever. Keyed by (model, exact batch of texts): the
retriever embeds all of a note's planned queries in one call, and that batch is identical
from one sweep run to the next.

A hit is still reported as a call (`cached=True`) with the original call's token count, so a
cached run's cost table says what the same run would cost live; its latency is the cache's."""

import hashlib
import json
import re
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from app.llm import IEmbeddingClient, LLMCallRecord, UsageRecorder, usage_scope
from app.llm.usage import current_purpose, default_recorder


class CachedEmbeddingClient(IEmbeddingClient):
    def __init__(self, inner: IEmbeddingClient, cache_dir: Path, *, recorder: UsageRecorder = default_recorder):
        self._inner = inner
        self._dir = cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", inner.model_name)
        self._recorder = recorder
        self.hits = 0
        self.misses = 0

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        path = self._path(texts)
        start = time.perf_counter()
        started_at = datetime.now(timezone.utc)

        if path.exists():
            entry = json.loads(path.read_text())
            self.hits += 1
            self._recorder.record(
                LLMCallRecord(
                    kind="embedding",
                    provider=entry["provider"],
                    model=self.model_name,
                    purpose=current_purpose(),
                    input_tokens=entry["input_tokens"],
                    output_tokens=None,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    started_at=started_at,
                    cached=True,
                )
            )
            return entry["vectors"]

        # The inner client records the live call itself (to every open scope); this scope
        # only reads that record back to keep its token count with the vectors.
        with usage_scope() as scope:
            vectors = await self._inner.embed(texts)
        live_call = scope.records[-1] if scope.records else None
        self.misses += 1

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "provider": live_call.provider if live_call else "unknown",
                    "input_tokens": live_call.input_tokens if live_call else None,
                    "texts": list(texts),
                    "vectors": vectors,
                }
            )
        )
        return vectors

    def _path(self, texts: Sequence[str]) -> Path:
        digest = hashlib.sha256(json.dumps([self.model_name, list(texts)], ensure_ascii=False).encode()).hexdigest()
        return self._dir / f"{digest}.json"
