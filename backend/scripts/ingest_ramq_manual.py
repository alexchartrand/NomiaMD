"""Turns a manually-saved export of the RAMQ manual into reference_data.json, in two
stages so a human review pass can sit between them (real regulatory text needs one — see
the plan this was built from).

    # Stage 1: parse the export, write a spreadsheet-friendly CSV for review.
    python scripts/ingest_ramq_manual.py extract --input data/raw/manuel.html \\
        --output data/raw/ramq_codes_raw.csv

    # ... open ramq_codes_raw.csv, fix anything flagged needs_review=1 or otherwise wrong ...

    # Stage 2: promote the reviewed CSV into the real reference_data.json.
    python scripts/ingest_ramq_manual.py promote --input data/raw/ramq_codes_raw.csv \\
        --output app/ramq/reference_data.json \\
        --source-document "Manuel des médecins omnipraticiens — Rémunération à l'acte"

Add --dry-run to either stage to print counts without writing the output file.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ramq.ingest.build_reference import extract_raw, parse_source, promote  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)

    p_extract = sub.add_parser("extract", help="Parse the source export into a review CSV.")
    p_extract.add_argument("--input", required=True, type=Path)
    p_extract.add_argument("--output", required=True, type=Path)
    p_extract.add_argument("--format", choices=["html", "pdf"], default=None)
    p_extract.add_argument("--dry-run", action="store_true")

    p_promote = sub.add_parser("promote", help="Promote a reviewed CSV into reference_data.json.")
    p_promote.add_argument("--input", required=True, type=Path)
    p_promote.add_argument("--output", required=True, type=Path)
    p_promote.add_argument("--source-document", required=True)
    p_promote.add_argument("--source-effective-date", default=None)
    p_promote.add_argument(
        "--skip-empty-fees", action="store_true", help="Exclude codes with no price data at all."
    )
    p_promote.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.stage == "extract":
        if args.dry_run:
            rows = parse_source(args.input, args.format)
            flagged = sum(1 for r in rows if r.needs_review)
            print(f"Would write {len(rows)} rows ({flagged} flagged needs_review) to {args.output}")
        else:
            count = extract_raw(args.input, args.output, args.format)
            print(f"Wrote {count} rows to {args.output}")

    elif args.stage == "promote":
        if args.dry_run:
            print(f"Dry run: would promote {args.input} -> {args.output}")
        else:
            count = promote(
                args.input,
                args.output,
                source_document=args.source_document,
                source_effective_date=args.source_effective_date,
                skip_empty_fees=args.skip_empty_fees,
            )
            print(f"Promoted {count} codes to {args.output}")


if __name__ == "__main__":
    main()
