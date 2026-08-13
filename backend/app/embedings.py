import os
from functools import lru_cache

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.mistralai import MistralAIEmbedding


@lru_cache(maxsize=1)
def get_embeding_model() -> BaseEmbedding:
    return MistralAIEmbedding(model_name=os.environ["MISTRAL_EMBEDDING_MODEL"],
                              api_key=os.environ["MISTRAL_API_KEY"])
