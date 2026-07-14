"""Runs billing-code extraction over a small hand-labeled eval set and reports how the
configured model (NOMIAMD_BASE_URL / NOMIAMD_MODEL) did against expected codes, plus a
sanity check that every supporting_quote is actually verbatim in the transcript.

Requires NOMIAMD_BASE_URL (and NOMIAMD_MODEL) to point at a running model server —
either the fake dev server (`make fake-llm`) or a real one. From backend/, with the venv
active:

    python scripts/eval_extraction.py [path/to/eval_set.jsonl]

Defaults to tests/fixtures/eval_billing_codes.jsonl, which is a *draft* fixture — most
entries have label_status "needs_physician_label" rather than real expected_codes, since
picking correct RAMQ billing codes requires domain expertise this script doesn't have.
Entries with expected_codes == [] are skipped for scoring (there's nothing to compare
against) but still run, so quote-grounding still gets checked on them.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must run before app.extraction.engine is imported below — it reads NOMIAMD_BASE_URL /
# NOMIAMD_MODEL at import time. Explicit path for the same reason as app/main.py: under
# a debugger, load_dotenv() searches os.getcwd() instead of walking up from this file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.extraction.engine import run_extraction  # noqa: E402
from app.sample_patients import get_sample_patient  # noqa: E402
from app.tasks.registry import get_task  # noqa: E402

DEFAULT_EVAL_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "eval_billing_codes.jsonl"


def load_eval_set(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def quote_is_grounded(transcript: str, quote: str) -> bool:
    """Loose containment check — whitespace-normalized, since models sometimes reflow
    line breaks in an otherwise-verbatim quote."""
    normalize = lambda s: " ".join(s.split())
    return normalize(quote) in normalize(transcript)


def main() -> None:
    eval_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EVAL_PATH
    entries = load_eval_set(eval_path)
    task = get_task("billing_codes")

    scored = 0
    total_precision = 0.0
    total_recall = 0.0
    ungrounded_quotes = 0
    total_quotes = 0

    for entry in entries:
        patient = get_sample_patient(entry["patient_id"])
        if patient is None:
            print(f"[skip] unknown patient_id {entry['patient_id']!r}")
            continue

        result = run_extraction(task, patient.transcript)
        returned_codes = {c.code for c in result.result.codes}
        expected_codes = set(entry.get("expected_codes") or [])

        for c in result.result.codes:
            total_quotes += 1
            if not quote_is_grounded(patient.transcript, c.supporting_quote):
                ungrounded_quotes += 1

        status = entry.get("label_status", "unknown")
        print(f"\n=== {entry['patient_id']} ({status}) ===")
        print(f"  returned: {sorted(returned_codes) or '(none)'}")

        if not expected_codes:
            print(f"  expected: (none labeled — {entry.get('label_notes', '')[:100]}...)")
            continue

        true_positives = returned_codes & expected_codes
        precision = len(true_positives) / len(returned_codes) if returned_codes else 0.0
        recall = len(true_positives) / len(expected_codes) if expected_codes else 0.0
        total_precision += precision
        total_recall += recall
        scored += 1
        print(f"  expected: {sorted(expected_codes)}")
        print(f"  precision={precision:.2f} recall={recall:.2f}")

    print(f"\n--- summary (model={result.model}) ---")
    if scored:
        print(f"scored entries: {scored} — avg precision={total_precision / scored:.2f}, "
              f"avg recall={total_recall / scored:.2f}")
    else:
        print("scored entries: 0 — no entries in the eval set have expected_codes yet; "
              "see label_status/label_notes in the fixture.")
    if total_quotes:
        print(f"quote grounding: {total_quotes - ungrounded_quotes}/{total_quotes} "
              f"supporting_quote(s) found verbatim in their transcript")


if __name__ == "__main__":
    main()
