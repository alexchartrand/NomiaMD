from typing import List

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

from app.lancedb.converter import IConverter
from app.lancedb.repository import IDocumentRepository
from app.ramq_chatbot.reference_expansion import ReferenceExpander


class RAMQManualRetriever(BaseRetriever):
    """Hybrid (vector + native FTS) search over the `documents-embeddings` LanceDB table —
    replaces the old VectorStoreIndex/BM25Retriever/QueryFusionRetriever stack (that BM25
    corpus scan and English stemmer only existed because the previous nested-struct table
    shape had no native FTS index; the flat table does — see ramq-ingestion's
    docs/plans/flat-lancedb-documents-table.md). No LLM query fan-out (that was
    query_generator.py's job, removed) and no RRF fusion step (app/lancedb/fusion.py's
    ReciprocalRankFuser, still used by billing_codes' retriever) — with a single query and a
    single hybrid_search call, there is nothing to fuse across.

    Async-only: IDocumentRepository has no sync query path, so _retrieve() (the sync
    BaseRetriever entry point) raises rather than pretending to support a code path nothing
    in this backend actually calls — app/ramq_chatbot/engine.py's RAMQManualQueryEngine only
    ever calls .aretrieve()."""

    def __init__(
        self,
        documents: IDocumentRepository,
        embed_model: BaseEmbedding,
        converter: IConverter,
        reference_expander: ReferenceExpander,
        similarity_top_k: int = 30,
    ):
        self._documents = documents
        self._embed_model = embed_model
        self._converter = converter
        self._reference_expander = reference_expander
        self._similarity_top_k = similarity_top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        raise NotImplementedError("RAMQManualRetriever is async-only — use aretrieve()")

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        vector = await self._embed_model.aget_query_embedding(query_bundle.query_str)
        hits = await self._documents.hybrid_search(
            text=query_bundle.query_str, vector=vector, k=self._similarity_top_k
        )
        nodes = [NodeWithScore(node=self._converter.convert(row), score=None) for row, _score in hits]

        return await self._reference_expander.aexpand(nodes)
