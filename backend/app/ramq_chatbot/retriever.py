import asyncio
from typing import List

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

from app.lancedb.converter import IConverter
from app.lancedb.repository import IDocumentRepository
from app.ramq_chatbot.fusion import ReciprocalRankFuser
from app.ramq_chatbot.query_generator import IQueryGenerator
from app.ramq_chatbot.reference_expansion import ReferenceExpander


class RAMQManualRetriever(BaseRetriever):
    """Hybrid (vector + native FTS) search over the `documents-embeddings` LanceDB table,
    fanned out across IQueryGenerator's generated queries and fused with
    ReciprocalRankFuser — replaces the old VectorStoreIndex/BM25Retriever/
    QueryFusionRetriever stack (that BM25 corpus scan and English stemmer only existed
    because the previous nested-struct table shape had no native FTS index; the flat table
    does — see ramq-ingestion's docs/plans/flat-lancedb-documents-table.md).

    Async-only: IDocumentRepository has no sync query path, so _retrieve() (the sync
    BaseRetriever entry point) raises rather than pretending to support a code path nothing
    in this backend actually calls — app/ramq_chatbot/engine.py's RAMQManualQueryEngine only
    ever calls .aretrieve()."""

    def __init__(
        self,
        documents: IDocumentRepository,
        embed_model: BaseEmbedding,
        query_generator: IQueryGenerator,
        fuser: ReciprocalRankFuser,
        converter: IConverter,
        reference_expander: ReferenceExpander,
        similarity_top_k: int = 20,
        num_queries: int = 3,
    ):
        self._documents = documents
        self._embed_model = embed_model
        self._query_generator = query_generator
        self._fuser = fuser
        self._converter = converter
        self._reference_expander = reference_expander
        self._similarity_top_k = similarity_top_k
        self._num_queries = num_queries
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        raise NotImplementedError("RAMQManualRetriever is async-only — use aretrieve()")

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        queries = await self._query_generator.agenerate(query_bundle.query_str, self._num_queries)
        vectors = await asyncio.gather(*(self._embed_model.aget_query_embedding(q) for q in queries))

        per_query_hits = await asyncio.gather(
            *(
                self._documents.hybrid_search(text=query, vector=vector, k=self._similarity_top_k)
                for query, vector in zip(queries, vectors)
            )
        )
        per_query_rows = [[row for row, _score in hits] for hits in per_query_hits]

        fused_rows = self._fuser.fuse(per_query_rows, top_k=self._similarity_top_k)
        nodes = [NodeWithScore(node=self._converter.convert(row), score=None) for row in fused_rows]

        return await self._reference_expander.aexpand(nodes)
