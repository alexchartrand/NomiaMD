"""Live smoke test for RAMQ code search (CodeRepository.hybrid_search, what
app/ramq_codes/retriever.py fans out over). Requires a real EMBEDDING_API_KEY and DB_PATH (see
.env) — this is a real network call against Mistral's embedding API plus a real read of the
current `codes_<rev>` LanceDB table (resolved through the `code_versions` registry), run
manually rather than as part of the pytest suite. From backend/, with the venv active:

    python scripts/ramq_vector_smoke_test.py

Checks two things pytest can't cheaply cover: that the corpus's embedding model assumption
(EMBEDDING_MODEL) actually matches whatever ramq-ingestion used to build the codes
table's vector column (a wrong model would still load and query
without error, just against numerically valid but semantically meaningless scores), and
that real French clinical text surfaces sensible, fully-hydrated candidates end to end —
mirrors ramq-ingestion's own scripts/codes_search_smoke_test.py.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Loads the repo-root .env — must run before the app imports below read their settings.
import app.config  # noqa: E402,F401

from app.llm import get_embedding_model
from app.lancedb import CodeRepository, LanceDB

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
        version = await db.code_tables.current_version()
        print(f"current codes table: {version.table_name} ({version.code_count} codes)")
        codes = CodeRepository(db.code_tables)
        embed_model = get_embedding_model()

        all_passed = True
        for query, expected_top_code in KNOWN_QUERIES:
            vector = await embed_model.aget_query_embedding(query)
            candidates = [row for row, _score in await codes.hybrid_search(query, vector, k=10)]
            numbers = [c.number for c in candidates]

            print(f"--- query: {query}")
            print(f"    candidates: {numbers}")
            if not candidates:
                print("    FAIL: no candidates returned")
                all_passed = False
            elif expected_top_code is not None and numbers[0] != expected_top_code:
                print(f"    FAIL: expected top code {expected_top_code}, got {numbers[0]}")
                all_passed = False
            elif not candidates[0].description or not candidates[0].header_path:
                print("    FAIL: top candidate missing hydrated row data (description/header_path)")
                all_passed = False
            else:
                print("    OK")
    finally:
        db.close()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
