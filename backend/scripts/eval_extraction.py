"""Runs billing-code extraction (via the three-stage transcript -> consultation_summary ->
context resolution -> billing_codes pipeline, see app/extraction/pipeline.py) over a small
hand-labeled eval set and reports how retrieval and selection each did, separately, against
the configured models (app/ramq_codes/task.py's MODEL for selection, engine.py's default for
the summary).

Splitting the two matters: a code the model never returned might be a selection miss (it saw
the right candidate and didn't pick it) or a retrieval miss (the candidate never made it into
the prompt at all) — those need different fixes. For every expected_codes entry this reports:

  - candidate recall: for each expected code, whether it was offered to the model exactly
    (present in the family-collapsed candidate list RAMQCodesRetriever produced), offered
    only as a same-family sibling (right taxonomy path, wrong variant — usually means an
    axis CodeFamilySelector couldn't resolve, or resolved against the wrong fact), or missing
    entirely (a real retrieval gap: query planning/embedding/FTS never surfaced it).
  - unresolved axes: whatever CodeFamilySelector flagged it couldn't disambiguate for this
    entry's context, printed so a miss is attributable to "no physician/patient_context was
    given" vs. a genuine gap.
  - selection precision/recall: the model's returned codes vs expected_codes, as before.

Requires MISTRAL_API_KEY to be set — either for a real Mistral API call, or with
MISTRAL_ENDPOINT pointed at the fake dev server (`make fake-llm`) for the summary/selection
calls. Retrieval always calls the real Mistral embeddings API regardless (no fake/override
exists for it — see scripts/fake_llm_server.py's module docstring), so DB_PATH must point at
a real `codes` table either way.

    python scripts/eval_extraction.py [path/to/eval_set.jsonl] [--retrieval-only]

--retrieval-only skips the billing_codes selection call (mistral-medium, the pricier of the
two calls) and only scores candidate recall/family accuracy — cheap enough to iterate
SummaryQueryPlanner/CodeFamilySelector against repeatedly. It still runs one
consultation_summary call per entry, since query planning needs the structured summary, not
the raw transcript.

Each eval_set.jsonl entry may carry optional `physician_context`/`patient_context` objects
(number_of_patients/physician_type/remuneration_type; age_years/is_registered/is_vulnerable)
— without them every axis stays unresolved and CodeFamilySelector keeps every family variant,
same as today's behavior. This is what makes the panel-size-ambiguous entries in the default
fixture (label_notes admitting "picked arbitrarily") actually gradeable: set the context and
the right variant becomes the only one offered.

Defaults to tests/fixtures/eval_billing_codes.jsonl, which is a *draft* fixture — most
entries have label_status "needs_physician_label" rather than real expected_codes, since
picking correct RAMQ billing codes requires domain expertise this script doesn't have.
Entries with expected_codes == [] are skipped for scoring (there's nothing to compare
against) but still run.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must run before app.extraction.engine is imported below — app.extraction.engine.get_client()
# reads MISTRAL_API_KEY. Explicit path for the same reason as app/main.py: under a debugger,
# load_dotenv() searches os.getcwd() instead of walking up from this file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.bootstrap import application_services  # noqa: E402
from app.extraction.engine import run_extraction  # noqa: E402
from app.lancedb import CodeRepository  # noqa: E402
from app.postgresdb import init_db  # noqa: E402
from app.ramq_codes import BillingCodesInput, BillingContext, PatientContext, PhysicianContext, build_ramq_retriever  # noqa: E402
from app.sample_patients import get_sample_patient  # noqa: E402
from app.tasks.registry import get_task  # noqa: E402

DEFAULT_EVAL_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "eval_billing_codes.jsonl"

# This script builds BillingContext directly from each fixture entry's physician_context/
# patient_context (see _context_from_entry) rather than going through
# BillingContextBuilder/PatientSuggestionService — deterministic and fixture-driven, with no
# dependency on a real physician login or patient roster.


def load_eval_set(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _context_from_entry(entry: dict) -> BillingContext:
    physician = entry.get("physician_context") or {}
    patient = entry.get("patient_context") or {}
    return BillingContext(
        physician=PhysicianContext(
            number_of_patients=physician.get("number_of_patients"),
            physician_type=physician.get("physician_type"),
            remuneration_type=physician.get("remuneration_type"),
        ),
        patient=PatientContext(
            age_years=patient.get("age_years"),
            is_registered=patient.get("is_registered"),
            is_vulnerable=patient.get("is_vulnerable"),
        ),
    )


@dataclass
class CandidateRecall:
    exact: set[str]
    family_only: set[str]
    missing: set[str]


async def _classify_candidates(
    codes_repo: CodeRepository, candidates, expected_codes: set[str]
) -> CandidateRecall:
    candidate_numbers = {c.number for c in candidates}
    candidate_header_paths = {c.header_path for c in candidates if c.header_path}

    exact: set[str] = set()
    family_only: set[str] = set()
    missing: set[str] = set()

    for code in expected_codes:
        if code in candidate_numbers:
            exact.add(code)
            continue
        try:
            row = await codes_repo.get_by_number(code)
        except ValueError:
            # Not in the codes table at all — a corpus gap (e.g. procedure codes the
            # ingested manual section doesn't cover yet), not a retrieval failure.
            missing.add(code)
            continue
        if row.header_path and row.header_path in candidate_header_paths:
            family_only.add(code)
        else:
            missing.add(code)

    return CandidateRecall(exact=exact, family_only=family_only, missing=missing)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("eval_path", nargs="?", default=str(DEFAULT_EVAL_PATH))
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip the billing_codes selection call; only score candidate recall/family accuracy.",
    )
    args = parser.parse_args()
    entries = load_eval_set(Path(args.eval_path))

    total_exact = total_family_only = total_missing = 0
    scored_selection = 0
    total_precision = 0.0
    total_recall = 0.0
    model = None

    await init_db()
    async with application_services() as db:
        codes_repo = CodeRepository(db.codes_table)
        retriever = build_ramq_retriever(codes_repo)

        for entry in entries:
            patient = get_sample_patient(entry["patient_id"])
            if patient is None:
                print(f"[skip] unknown patient_id {entry['patient_id']!r}")
                continue

            context = _context_from_entry(entry)
            status = entry.get("label_status", "unknown")
            print(f"\n=== {entry['patient_id']} ({status}) ===")

            summary_result = await run_extraction(get_task("consultation_summary"), patient.transcript)
            summary = summary_result.result

            collapse_result = await retriever.aretrieve(summary, context)
            print(f"  unresolved axes: {collapse_result.unresolved_axes or '(none)'}")

            expected_codes = set(entry.get("expected_codes") or [])
            if expected_codes:
                recall = await _classify_candidates(codes_repo, collapse_result.candidates, expected_codes)
                total_exact += len(recall.exact)
                total_family_only += len(recall.family_only)
                total_missing += len(recall.missing)
                print(
                    f"  candidate recall: exact={sorted(recall.exact)} "
                    f"family-only={sorted(recall.family_only)} missing={sorted(recall.missing)}"
                )
            else:
                print(f"  expected: (none labeled — {entry.get('label_notes', '')[:100]}...)")

            if args.retrieval_only:
                continue

            billing_input = BillingCodesInput(summary=summary, transcript=patient.transcript, context=context)
            billing_result = await run_extraction(get_task("billing_codes"), billing_input)
            model = billing_result.model
            returned_codes = {c.code for c in billing_result.result.codes}
            print(f"  returned: {sorted(returned_codes) or '(none)'}")

            if not expected_codes:
                continue

            true_positives = returned_codes & expected_codes
            precision = len(true_positives) / len(returned_codes) if returned_codes else 0.0
            recall_score = len(true_positives) / len(expected_codes) if expected_codes else 0.0
            total_precision += precision
            total_recall += recall_score
            scored_selection += 1
            print(f"  expected: {sorted(expected_codes)}")
            print(f"  selection precision={precision:.2f} recall={recall_score:.2f}")

    total_expected_positions = total_exact + total_family_only + total_missing
    print("\n--- summary ---")
    if total_expected_positions:
        print(
            f"candidate recall over {total_expected_positions} expected-code position(s): "
            f"exact {total_exact} ({total_exact / total_expected_positions:.0%}), "
            f"family-only {total_family_only} ({total_family_only / total_expected_positions:.0%}), "
            f"missing {total_missing} ({total_missing / total_expected_positions:.0%})"
        )
    else:
        print("no expected_codes labeled in this eval set — nothing to score on candidate recall")

    if args.retrieval_only:
        print("--retrieval-only: selection not run")
    elif scored_selection:
        print(
            f"selection (model={model}) over {scored_selection} entries: "
            f"avg precision={total_precision / scored_selection:.2f}, "
            f"avg recall={total_recall / scored_selection:.2f}"
        )
    else:
        print("selection: no entries scored — see label_status/label_notes in the fixture")


if __name__ == "__main__":
    asyncio.run(main())
