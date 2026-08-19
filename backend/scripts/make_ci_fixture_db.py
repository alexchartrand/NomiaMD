"""Creates throwaway `codes` and `code-embeddings` LanceDB tables at DB_PATH — CI-only
tooling, not used in prod.

app/lancedb/db.py's CodeTable opens the `codes` table eagerly at construction time
(db.open_table(...)), and app/ramq_codes/retriever.py's RAMQCodesRetriever now calls
vector_store.get_nodes() (to build a BM25Retriever) eagerly in __init__ too — both
constructions happen at import time via app/tasks/registry.py, so pytest collection fails
without both tables on disk, even though no test ever actually queries either (tests/
conftest.py's autouse small_reference_table fixture replaces both with stubs before any
test runs). This script creates just enough of each real table — correct schema, near-zero
rows — to satisfy those import-time opens, without needing a real ramq-ingestion-produced
database in CI.

`codes` schema mirrors app/lancedb/models.py's CodeRow, which itself mirrors
ramq-ingestion's src/embedding/code_table_schema.py. `code-embeddings` is created via
LanceDBVectorStore.add() (rather than a hand-written pyarrow schema) so its columns match
whatever that llama_index integration actually expects, since RAMQCodesRetriever opens it
through the same class (app/lancedb/factory.py's get_vectorstore).
"""

import os

import lancedb
import pyarrow as pa
from llama_index.core.schema import TextNode
from llama_index.vector_stores.lancedb import LanceDBVectorStore

SCHEMA = pa.schema([
    pa.field("number", pa.string()),
    pa.field("description", pa.string()),
    pa.field("when_to_use", pa.list_(pa.string())),
    pa.field("rules", pa.list_(pa.string())),
    pa.field("fees", pa.list_(pa.struct([
        pa.field("amount", pa.float64()),
        pa.field("when_to_use", pa.string()),
        pa.field("majoration", pa.string()),
    ]))),
    pa.field("confidence", pa.float64()),
])

# Matches mistral-embed's output dimension (app/embedings.py's MistralAIEmbedding) — the
# actual value doesn't matter here since no test ever runs a real similarity search against
# this fixture, only construction (BM25Retriever.from_defaults / VectorStoreIndex.from_vector_store).
EMBEDDING_DIM = 1024


def main() -> None:
    db_path = os.environ["DB_PATH"]

    db = lancedb.connect(db_path)
    db.create_table("codes", schema=SCHEMA)

    vector_store = LanceDBVectorStore(uri=db_path, table_name="code-embeddings", flat_metadata=False)
    placeholder = TextNode(
        text="placeholder",
        metadata={"number": "0000"},
        embedding=[0.0] * EMBEDDING_DIM,
    )
    vector_store.add([placeholder])


if __name__ == "__main__":
    main()
