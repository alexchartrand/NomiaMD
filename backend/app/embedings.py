from functools import lru_cache

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.mistralai import MistralAIEmbedding

from app.config import settings


@lru_cache(maxsize=1)
def get_embeding_model() -> BaseEmbedding:
    return MistralAIEmbedding(model_name=settings.mistral_embedding_model,
                              api_key=settings.mistral_api_key)
