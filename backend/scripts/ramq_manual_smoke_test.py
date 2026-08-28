"""Live smoke test for the RAMQ manual chatbot (app/ramq_chatbot/), modeled on
scripts/ramq_vector_smoke_test.py. Requires a real MISTRAL_API_KEY and RAMQ_CHATBOT_DB_PATH
(see .env) — this makes real network calls against Mistral's completion/embedding APIs plus
a real read of the local `documents-embeddings` LanceDB table, run manually rather than as
part of the pytest suite. From backend/, with the venv active:

    python scripts/ramq_manual_smoke_test.py

Checks the three DocumentRepository access patterns pytest only ever exercises against a
tiny synthetic fixture (tests/test_lancedb_document_repository.py), against the real,
ramq-ingestion-built table, plus one full /query round trip through
RAMQManualQueryEngine.acustom_query — the same call app/ramq_chatbot/router.py makes.

Replaces the old scripts/simple_query.py: that script predated RAMQManualRetriever's
required `reference_expander` argument and had been broken (TypeError on construction) since
that argument was added — this one is actually run, so it can't silently rot the same way.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.lancedb import LanceDB  # noqa: E402
from app.ramq_chatbot.factory import init_ramq_query_engine, get_ramq_query_engine  # noqa: E402

# A handful of unambiguous cases from the real manual/table (see ramq-ingestion's
# docs/plans/flat-lancedb-documents-table.md "End-to-end proof" section for where these
# expected counts come from).
KNOWN_SECTION_NUMBER = "2.2.6"
KNOWN_CODE_REFERENCE = "00837"
KNOWN_QUERY = "majoration"


async def main() -> None:
    db = await LanceDB.open()
    all_passed = True
    try:
        # -- get_by_section_number ------------------------------------------------------
        section_rows = await db.documents.get_by_section_number(KNOWN_SECTION_NUMBER)
        print(f"--- get_by_section_number({KNOWN_SECTION_NUMBER!r}): {len(section_rows)} row(s)")
        if not section_rows:
            print("    FAIL: expected at least one row")
            all_passed = False
        else:
            print("    OK")

        # -- get_by_code_reference --------------------------------------------------------
        code_rows = await db.documents.get_by_code_reference(KNOWN_CODE_REFERENCE)
        print(f"--- get_by_code_reference({KNOWN_CODE_REFERENCE!r}): {len(code_rows)} row(s)")
        if not code_rows:
            print("    FAIL: expected at least one row")
            all_passed = False
        else:
            print("    OK")

        # -- hybrid_search ------------------------------------------------------------------
        from app.embedings import get_embeding_model

        embed_model = get_embeding_model()
        vector = await embed_model.aget_query_embedding(KNOWN_QUERY)
        hits = await db.documents.hybrid_search(text=KNOWN_QUERY, vector=vector, k=5)
        print(f"--- hybrid_search({KNOWN_QUERY!r}): {len(hits)} hit(s)")
        if not hits:
            print("    FAIL: expected at least one hit")
            all_passed = False
        else:
            print("    OK")

        # -- one full /query round trip -----------------------------------------------------
        init_ramq_query_engine(db.codes, db.documents)
        engine = get_ramq_query_engine()
        question = "Quelle est la majoration de nuit?"
        answer = await engine.acustom_query(question)
        print(f"--- /query: {question!r}")
        print(f"    answer: {answer[:200]}{'...' if len(answer) > 200 else ''}")
        if not answer.strip():
            print("    FAIL: empty answer")
            all_passed = False
        else:
            print("    OK")
    finally:
        db.close()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
