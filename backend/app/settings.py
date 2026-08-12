import os
from functools import cache
from dotenv import load_dotenv

from llama_index.core import Settings
from llama_index.embeddings.mistralai import MistralAIEmbedding
from llama_index.llms.mistralai import MistralAI

load_dotenv()

@cache
def configure_settings():
    Settings.embed_model = MistralAIEmbedding(api_key=os.environ["MISTRAL_API_KEY"])
    Settings.llm = MistralAI(model="mistral-medium-latest", api_key=os.environ["MISTRAL_API_KEY"])