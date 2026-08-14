from dotenv import load_dotenv
from pathlib import Path
import os

from llama_index.vector_stores.lancedb import LanceDBVectorStore

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.embedings import get_embeding_model
from app.ramq_codes.retriever import RAMQCodesRetriever

EMBEDDINGS_TABLE_NAME = "code-embeddings"
QUERY="J'ai vu un patient en clinique au sans rendez-vous. C'est un de mes patients et j'ai plus de 500 patients."

def test():
    persist_dir = os.environ["DB_PATH"]
    vector_store = LanceDBVectorStore(uri=persist_dir, table_name=EMBEDDINGS_TABLE_NAME, flat_metadata=False)

    retriever = RAMQCodesRetriever(
        vector_store=vector_store,
        embed_model=get_embeding_model())
    nodes = retriever.retrieve(QUERY)

    for node in nodes:
        print(f"score: {node.score}, code: {node.node.metadata.get('number')}")

if __name__ == "__main__":
    test()