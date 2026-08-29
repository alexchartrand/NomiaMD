"""Live smoke test for RAMQ candidate retrieval (app/ramq_codes/retriever.py). Requires a
real MISTRAL_API_KEY and DB_PATH (see .env) — this is a real network call against Mistral's
embedding API plus a real read of the local `codes` LanceDB table, run manually rather than
as part of the pytest suite. From backend/, with the venv active:

    python scripts/ramq_vector_smoke_test.py

Checks two things pytest can't cheaply cover: that the corpus's embedding model assumption
in retriever.py (MISTRAL_EMBEDDING_MODEL) actually matches whatever ramq-ingestion used
to build the `codes` table's vector column (a wrong model would still load and query
without error, just against numerically valid but semantically meaningless scores), and
that real French clinical text surfaces sensible, fully-hydrated candidates end to end —
mirrors ramq-ingestion's own scripts/codes_search_smoke_test.py.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lancedb import CodeRepository, LanceDB
from app.ramq_codes.factory import build_ramq_retriever

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


async def main() -> None:
    db = await LanceDB.open()
    try:
        codes = CodeRepository(db.codes_table)
        retriever = build_ramq_retriever(codes)

        all_passed = True
        for query, expected_top_code in KNOWN_QUERIES:
            candidates = await retriever.aretrieve(query)
            numbers = [c.number for c in candidates]

            print(f"--- query: {query}")
            print(f"    candidates: {numbers}")
            if not candidates:
                print("    FAIL: no candidates returned")
                all_passed = False
            elif expected_top_code is not None and numbers[0] != expected_top_code:
                print(f"    FAIL: expected top code {expected_top_code}, got {numbers[0]}")
                all_passed = False
            elif not candidates[0].libelle or not candidates[0].description:
                print("    FAIL: top candidate missing hydrated row data (libelle/description)")
                all_passed = False
            else:
                print("    OK")
    finally:
        db.close()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
