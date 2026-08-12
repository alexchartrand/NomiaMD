
from llama_index.core import Settings, PromptTemplate
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.query_engine import CustomQueryEngine

class RAMQManualQueryEngine(CustomQueryEngine):

    retriever: BaseRetriever
    qa_prompt: PromptTemplate = PromptTemplate(
    "You are a RAMQ billing specialist. Context information is below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Given the context information and not prior knowledge, "
    "answer the query.\n"
    "Query: {query_str}\n"
    "Answer must be in french. Specify the source of your answer.")

    def custom_query(self, query_str: str):
        nodes = self.retriever.retrieve(query_str)

        context_str = "\n\n".join([n.node.get_content() for n in nodes])
        response = Settings.llm.complete(
            self.qa_prompt.format(context_str=context_str, query_str=query_str)
        )

        return response