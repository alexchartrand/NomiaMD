"""Live smoke test for RAMQ candidate retrieval (app/ramq_codes/retriever.py). Requires a
real MISTRAL_API_KEY and DB_PATH (see .env) — this is a real network call against Mistral's
embedding API plus a real read of the local LanceDB `codes` table, run manually rather than
as part of the pytest suite. From backend/, with the venv active:

    python scripts/ramq_vector_smoke_test.py

Checks two things pytest can't cheaply cover: that the corpus's embedding model assumption
in retriever.py (MISTRAL_EMBED_MODEL) actually matches whatever ramq-ingestion used
to build the `codes` table (a wrong model would still load and query without error, just
against numerically valid but semantically meaningless scores), and that real French
clinical text surfaces sensible candidates end to end.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import os

from app.embedings import get_embeding_model  # noqa: E402
from app.ramq_codes.retriever import DEFAULT_TABLE_NAME, RAMQCodesRetriever, candidates_from_nodes  # noqa: E402
from app.ramq_codes.vector_store import LanceVectorStore  # noqa: E402

# (query, expected top-ranked code) — a handful of unambiguous cases from the real manual.
KNOWN_QUERIES = [
    (
        "Supplément pour la communication par l'intermédiaire d'un interprète, en cabinet.",
        "15188",
    ),
    (
        "Patient avec douleur thoracique et suspicion d'infarctus, transfert pour angioplastie.",
        None,  # no single unambiguous expected code — just checking it's non-empty
    ),
]


def main() -> None:
    vector_store = LanceVectorStore(persist_dir=os.environ["DB_PATH"]).get_vector_store(DEFAULT_TABLE_NAME)
    retriever = RAMQCodesRetriever(vector_store, get_embeding_model())

    all_passed = True
    for query, expected_top_code in KNOWN_QUERIES:
        results = candidates_from_nodes(retriever.retrieve(query))
        codes = [c.code for c in results]
        print(f"--- query: {query}")
        print(f"    candidates: {codes}")
        if not codes:
            print("    FAIL: no candidates returned")
            all_passed = False
        elif expected_top_code is not None and codes[0] != expected_top_code:
            print(f"    FAIL: expected top code {expected_top_code}, got {codes[0]}")
            all_passed = False
        else:
            print("    OK")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
