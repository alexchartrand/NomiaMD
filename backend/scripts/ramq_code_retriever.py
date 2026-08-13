from dotenv import load_dotenv
from pathlib import Path
import os

from llama_index.vector_stores.lancedb import LanceDBVectorStore

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.embedings import get_embeding_model
from app.ramq.vector_retrieval import RAMQCodesRetriever

TABLE_NAME="codes"
QUERY="J'ai vu un patien en clinique au sans rendez-vous. C'est un de mes patients et j'ai plus de 500 patients."

def test():
    vector_store = LanceDBVectorStore(uri=os.environ["DB_PATH"], table_name=TABLE_NAME, flat_metadata=False)
    retriever = RAMQCodesRetriever(
        vector_store=vector_store, 
        embed_model=get_embeding_model())
    nodes = retriever.retrieve(QUERY)

    for node in nodes:
        print(f"score: {node.score}, code: {node.node.metadata.get('number')}, description: {node.node.metadata.get('description')}")

if __name__ == "__main__":
    test()