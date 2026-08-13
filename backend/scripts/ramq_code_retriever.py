from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.embedings import get_embeding_model
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.ramq_codes.vector_store import LanceCodeTableReader

TABLE_NAME="codes"
QUERY="J'ai vu un patien en clinique au sans rendez-vous. C'est un de mes patients et j'ai plus de 500 patients."

def test():
    table = LanceCodeTableReader(persist_dir=os.environ["DB_PATH"]).open_table(TABLE_NAME)
    retriever = RAMQCodesRetriever(
        table=table,
        embed_model=get_embeding_model())
    nodes = retriever.retrieve(QUERY)

    for node in nodes:
        print(f"score: {node.score}, code: {node.node.metadata.get('number')}, description: {node.node.metadata.get('description')}")

if __name__ == "__main__":
    test()