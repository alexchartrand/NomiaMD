import os

from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.ramq_chatbot.engine import RAMQManualQueryEngine
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.embedings import get_embeding_model

TABLE_NAME = "manuel-omnipraticiens"

def query_test_with_custom_query_engine():
    query = "J'ai vu une de mes patients en clinique au sans rendez-vous. Quels sont les codes associés?"
    # reload the LanceDB-backed index (flat_metadata must match what it was built with)
    vector_store = LanceDBVectorStore(uri=os.environ["DB_PATH"], table_name=TABLE_NAME, flat_metadata=False)
    api_key = os.environ["MISTRAL_API_KEY"]
    llm = MistralAI(model="mistral-medium-latest", api_key=api_key, temperature=0, max_tokens=4096,)

    retriever = RAMQManualRetriever(
        vector_store=vector_store, llm=llm, embed_model=get_embeding_model(), debug=True)

    query_engine = RAMQManualQueryEngine(retriever=retriever, llm=llm)

    response = query_engine.query(query)
    print(response)

if __name__ == "__main__":
    query_test_with_custom_query_engine()