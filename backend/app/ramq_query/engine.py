
from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.query_engine import CustomQueryEngine

SYSTEM_PROMPT = """\
You are a RAMQ billing specialist. 

Context information is below:
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {query_str}
Rules:
- Answer must be in french. 
- Specify the source of every answers.
"""

#TODO: Change llm.complete for llm.chat
class RAMQManualQueryEngine(CustomQueryEngine):

    retriever: BaseRetriever
    llm: LLM

    def custom_query(self, query_str: str):
        nodes = self.retriever.retrieve(query_str)

        context_str = "\n\n".join([n.node.get_content() for n in nodes])
        response = self.llm.complete(
            SYSTEM_PROMPT.format(context_str=context_str, query_str=query_str))

        return response