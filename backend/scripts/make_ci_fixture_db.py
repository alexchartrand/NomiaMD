"""Creates an empty LanceDB `codes` table at DB_PATH — CI-only tooling, not used in prod.

app/lancedb/db.py's CodeTable opens the `codes` table eagerly at construction time
(db.open_table(...)), and that construction happens at import time via
app/tasks/registry.py — so pytest collection fails without a real `codes` table on disk,
even though no test ever actually queries it (tests/conftest.py's autouse
small_reference_table fixture replaces it with a stub before any test runs). This script
creates just enough of a real table — correct schema, zero rows — to satisfy that
import-time open, without needing a real ramq-ingestion-produced database in CI.

Schema mirrors app/lancedb/models.py's CodeRow, which itself mirrors ramq-ingestion's
src/embedding/code_table_schema.py.
"""

import os

import lancedb
import pyarrow as pa

SCHEMA = pa.schema([
    pa.field("number", pa.string()),
    pa.field("description", pa.string()),
    pa.field("when_to_use", pa.list_(pa.string())),
    pa.field("rules", pa.list_(pa.string())),
    pa.field("fees", pa.list_(pa.struct([
        pa.field("amount", pa.float64()),
        pa.field("when_to_use", pa.string()),
        pa.field("majoration", pa.string()),
    ]))),
    pa.field("confidence", pa.float64()),
])


def main() -> None:
    db = lancedb.connect(os.environ["DB_PATH"])
    db.create_table("codes", schema=SCHEMA)


if __name__ == "__main__":
    main()
