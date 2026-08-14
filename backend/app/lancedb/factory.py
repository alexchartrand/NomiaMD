from functools import cache
import os

import lancedb
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from app.lancedb.db import CodeTable

EMBEDDINGS_TABLE_NAME = "code-embeddings"

db_dir = os.environ["DB_PATH"]

@cache
def get_database():
    return lancedb.connect(db_dir)

@cache
def get_vectorstore():
    return LanceDBVectorStore(uri=db_dir, table_name=EMBEDDINGS_TABLE_NAME, flat_metadata=False)

def get_codes_table_reader():
    return CodeTable(get_database())