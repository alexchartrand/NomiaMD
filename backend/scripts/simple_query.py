import os

from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.ramq_query.query_engine import RAMQManualQueryEngine
from app.ramq_query.retriever import RAMQManualRetriever

TABLE_NAME = "manuel-omnipraticiens"

def query_test_with_custom_query_engine():
    query = "J'ai eu à me rendre à l'hopital en urgence pour voir un patient. Qu'est-ce que je dois facturer? il était 3h am"
    # reload the LanceDB-backed index (flat_metadata must match what it was built with)
    vector_store = LanceDBVectorStore(uri=os.environ["DB_PATH"], table_name=TABLE_NAME, flat_metadata=False)

    retriever = RAMQManualRetriever(vector_store=vector_store)

    query_engine = RAMQManualQueryEngine(retriever=retriever,)

    response = query_engine.query(query)
    print(response)

def query_test():
    # reload the LanceDB-backed index (flat_metadata must match what it was built with)
    vector_store = LanceDBVectorStore(uri=os.environ["DB_PATH"], table_name=TABLE_NAME, flat_metadata=False)
    index = VectorStoreIndex.from_vector_store(vector_store)

    query_engine = index.as_query_engine(
    response_mode="compact",verbose=True,)
    response = query_engine.query("J'ai eu à me rendre à l'hopita en urgence pour voir un patient. Qu'est-ce que je dois facturer?")
    print(response)

if __name__ == "__main__":
    query_test_with_custom_query_engine()