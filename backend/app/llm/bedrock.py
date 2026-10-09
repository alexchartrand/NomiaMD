"""Query embeddings from a Bedrock-hosted model (Cohere Embed v4 or v3), to search the
candidate codes tables ramq-ingestion embeds with the same model. Embeddings have no
OpenAI-compatible endpoint on Bedrock, so this is the one embedding client that doesn't go
through app/llm/openai_client.py: it calls InvokeModel through boto3.

Each request body mirrors ramq-ingestion's src/ramq_ingestion/shared/bedrock_text_embedder.py,
with one deliberate difference: Cohere models are asymmetric, and ramq-ingestion embeds the
corpus as `search_document`, so queries go out as `search_query`. The output dimension must
match too, which the startup guard (embedding_guard.py) checks.

Credentials come from the AWS SDK's own chain (`aws login`), never from settings. Like every
query embedding, the texts derive from the transcript and carry PHI: only synthetic notes
may go to Bedrock until the hosting Region is cleared for real data."""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config

from app.config import settings
from app.llm.client import IEmbeddingClient
from app.llm.provider import EmbeddingModelProvider
from app.llm.usage import LLMCallRecord, UsageRecorder, current_purpose, default_recorder

# Bedrock reports the input token count in a response header, not in the body.
INPUT_TOKEN_COUNT_HEADER = "x-amzn-bedrock-input-token-count"


class IBedrockEmbeddingFormat(ABC):
    """One model family's InvokeModel request and response body."""

    @abstractmethod
    def body(self, texts: list[str]) -> dict[str, Any]:
        pass

    @abstractmethod
    def vectors(self, payload: dict[str, Any]) -> list[list[float]]:
        pass


class CohereEmbedV4Format(IBedrockEmbeddingFormat):
    """Cohere Embed v4 at 1024 dimensions, ramq-ingestion's default for it."""

    output_dimension = 1024

    def body(self, texts: list[str]) -> dict[str, Any]:
        return {
            "texts": texts,
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": self.output_dimension,
            # Fail on an oversized text rather than embed half of it.
            "truncate": "NONE",
        }

    def vectors(self, payload: dict[str, Any]) -> list[list[float]]:
        return payload["embeddings"]["float"]


class CohereEmbedV3Format(IBedrockEmbeddingFormat):
    """Cohere Embed v3 (multilingual or English): 1024 dimensions, fixed."""

    def body(self, texts: list[str]) -> dict[str, Any]:
        return {"texts": texts, "input_type": "search_query", "truncate": "NONE"}

    def vectors(self, payload: dict[str, Any]) -> list[list[float]]:
        return payload["embeddings"]


def embedding_format_for(model_id: str) -> IBedrockEmbeddingFormat:
    if "cohere.embed-v4" in model_id:
        return CohereEmbedV4Format()
    if "cohere.embed-multilingual-v3" in model_id or "cohere.embed-english-v3" in model_id:
        return CohereEmbedV3Format()
    raise ValueError(f"No Bedrock embedding format for {model_id!r}; supported: Cohere Embed v3 and v4")


class BedrockEmbeddingClient(IEmbeddingClient):
    """`client` is a boto3 `bedrock-runtime` client. boto3 is synchronous, so each call runs
    in a worker thread; its clients are thread-safe."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        embedding_format: IBedrockEmbeddingFormat,
        recorder: UsageRecorder = default_recorder,
    ):
        self._client = client
        self._model = model
        self._format = embedding_format
        self._recorder = recorder

    @property
    def provider_name(self) -> str:
        return BedrockEmbeddingProvider.name

    @property
    def model_name(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._client.invoke_model,
                modelId=self._model,
                body=json.dumps(self._format.body(list(texts))),
                contentType="application/json",
                accept="application/json",
            )
            vectors = self._format.vectors(json.loads(response["body"].read()))
            if len(vectors) != len(texts):
                raise RuntimeError(f"{self._model} returned {len(vectors)} vectors for {len(texts)} texts")
        except Exception as exc:
            self._record(started_at, start, input_tokens=None, error=f"{type(exc).__name__}: {exc}")
            raise

        self._record(started_at, start, input_tokens=_input_tokens(response))
        return vectors

    def _record(self, started_at: datetime, start: float, *, input_tokens: int | None, error: str | None = None) -> None:
        self._recorder.record(
            LLMCallRecord(
                kind="embedding",
                provider=self.provider_name,
                model=self._model,
                purpose=current_purpose(),
                input_tokens=input_tokens,
                output_tokens=None,
                latency_ms=(time.perf_counter() - start) * 1000,
                started_at=started_at,
                error=error,
            )
        )


def _input_tokens(response: dict[str, Any]) -> int | None:
    value = response.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get(INPUT_TOKEN_COUNT_HEADER)
    return int(value) if value is not None else None


class BedrockEmbeddingProvider(EmbeddingModelProvider):
    """Amazon Bedrock's InvokeModel. EMBEDDING_MODEL is the Bedrock model id ramq-ingestion
    embedded the table with (e.g. `cohere.embed-v4:0`), required. BEDROCK_REGION overrides
    the Region the AWS SDK's own configuration picks."""

    name = "bedrock"

    def build(self) -> IEmbeddingClient:
        model = settings.embedding_model
        if not model:
            raise RuntimeError("EMBEDDING_PROVIDER=bedrock requires EMBEDDING_MODEL (e.g. cohere.embed-v4:0)")
        embedding_format = embedding_format_for(model)
        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            config=Config(retries={"max_attempts": 5, "mode": "adaptive"}, connect_timeout=10),
        )
        return BedrockEmbeddingClient(client, model=model, embedding_format=embedding_format)
