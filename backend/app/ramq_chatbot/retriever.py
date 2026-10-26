import logging
import time
from abc import ABC, abstractmethod

from app.lancedb.converter import IConverter
from app.lancedb.models import DocumentRow
from app.lancedb.repository import IDocumentRepository
from app.llm import IEmbeddingClient, call_purpose
from app.ramq_chatbot.chunks import ManualChunk, ScoredChunk
from app.ramq_chatbot.reference_expansion import ReferenceExpander

logger = logging.getLogger(__name__)


class IManualRetriever(ABC):
    @abstractmethod
    async def aretrieve(self, query: str) -> list[ScoredChunk]:
        pass


class RAMQManualRetriever(IManualRetriever):
    """Hybrid (vector + native FTS) search over the `documents-embeddings` LanceDB table —
    replaces the old VectorStoreIndex/BM25Retriever/QueryFusionRetriever stack (that BM25
    corpus scan and English stemmer only existed because the previous nested-struct table
    shape had no native FTS index; the flat table does — see ramq-ingestion's
    docs/plans/flat-lancedb-documents-table.md). No LLM query fan-out (that was
    query_generator.py's job, removed) and no RRF fusion step (app/lancedb/fusion.py's
    ReciprocalRankFuser, still used by billing_codes' retriever) — with a single query and a
    single hybrid_search call, there is nothing to fuse across.

    Async-only: IDocumentRepository has no sync query path."""

    def __init__(
        self,
        documents: IDocumentRepository,
        embedding_client: IEmbeddingClient,
        converter: IConverter[DocumentRow, ManualChunk],
        reference_expander: ReferenceExpander,
        similarity_top_k: int = 30,
    ):
        self._documents = documents
        self._embedding_client = embedding_client
        self._converter = converter
        self._reference_expander = reference_expander
        self._similarity_top_k = similarity_top_k

    async def aretrieve(self, query: str) -> list[ScoredChunk]:
        retriever_start = time.perf_counter()

        with call_purpose("ramq_chatbot.retrieval"):
            vector = await self._embedding_client.embed_query(query)

        db_start = time.perf_counter()
        hits = await self._documents.hybrid_search(text=query, vector=vector, k=self._similarity_top_k)
        db_duration_ms = (time.perf_counter() - db_start) * 1000

        chunks = [ScoredChunk(chunk=self._converter.convert(row), score=score) for row, score in hits]
        expanded = await self._reference_expander.aexpand(chunks)

        retriever_duration_ms = (time.perf_counter() - retriever_start) * 1000
        logger.debug(
            "RAMQManualRetriever.aretrieve timing",
            extra={
                "retriever_duration_ms": round(retriever_duration_ms, 1),
                "db_duration_ms": round(db_duration_ms, 1),
            },
        )
        logger.debug(
            "RAMQManualRetriever.aretrieve result",
            extra={
                "chunks": [
                    {
                        "id": hit.chunk.id,
                        "title": hit.chunk.metadata.get("title"),
                        "section_number": hit.chunk.metadata.get("section_number"),
                        "is_expansion": hit.chunk.metadata.get("is_expansion", False),
                        "text": hit.chunk.text[:200],
                    }
                    for hit in expanded
                ],
                "chunk_count": len(expanded),
            },
        )

        return expanded
