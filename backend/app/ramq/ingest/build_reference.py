"""Two independently-callable stages between a source manual export and the promoted
reference_data.json: extract_raw() for a spreadsheet-friendly review pass, and promote()
to turn the (possibly hand-edited) reviewed file into the final reference table.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.ramq.ingest.models import RawCodeRow, RawFeeVariant

_FEE_COLUMNS = 4  # matches parse_html's continuation-merge cap; see its docstring

CSV_FIELDS = ["code", "description", "category", "unit", "source_ref", "needs_review"]
for _i in range(1, _FEE_COLUMNS + 1):
    CSV_FIELDS += [f"fee{_i}_context", f"fee{_i}_price_cad", f"fee{_i}_percentage"]


def _detect_format(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "pdf"
    if path.suffix.lower() in (".html", ".htm"):
        return "html"
    raise ValueError(f"Can't infer format from extension: {path}")


def parse_source(path: Path, fmt: str | None = None) -> list[RawCodeRow]:
    fmt = fmt or _detect_format(path)
    if fmt == "html":
        from app.ramq.ingest.parse_html import parse

        return parse(path)
    if fmt == "pdf":
        raise NotImplementedError(
            "PDF parsing isn't implemented yet — the manual export used so far has been "
            "HTML. Add app/ramq/ingest/parse_pdf.py (pdfplumber-based, per the plan) if a "
            "PDF export needs to be ingested."
        )
    raise ValueError(f"Unknown format: {fmt!r}")


def extract_raw(source_path: Path, out_path: Path, fmt: str | None = None) -> int:
    """Stage 1: parse the source export and write a spreadsheet-friendly CSV for human
    review. Returns the row count."""
    rows = parse_source(Path(source_path), fmt)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            record = {
                "code": row.code,
                "description": row.description,
                "category": row.category,
                "unit": row.unit or "",
                "source_ref": row.source_ref or "",
                "needs_review": "1" if row.needs_review else "",
            }
            for i in range(_FEE_COLUMNS):
                prefix = f"fee{i + 1}_"
                if i < len(row.fees):
                    fee = row.fees[i]
                    record[prefix + "context"] = fee.context_label
                    record[prefix + "price_cad"] = "" if fee.price_cad is None else fee.price_cad
                    record[prefix + "percentage"] = "" if fee.percentage is None else fee.percentage
                else:
                    record[prefix + "context"] = ""
                    record[prefix + "price_cad"] = ""
                    record[prefix + "percentage"] = ""
            writer.writerow(record)

    return len(rows)


def _read_reviewed_csv(path: Path) -> list[RawCodeRow]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for record in csv.DictReader(f):
            if not record.get("code"):
                continue
            fees = []
            for i in range(1, _FEE_COLUMNS + 1):
                context = record.get(f"fee{i}_context", "")
                price = record.get(f"fee{i}_price_cad", "")
                pct = record.get(f"fee{i}_percentage", "")
                if not context and not price and not pct:
                    continue
                fees.append(
                    RawFeeVariant(
                        context_label=context,
                        price_cad=float(price) if price else None,
                        percentage=float(pct) if pct else None,
                    )
                )
            rows.append(
                RawCodeRow(
                    code=record["code"],
                    description=record["description"],
                    category=record["category"],
                    fees=fees,
                    unit=record.get("unit") or None,
                    source_ref=record.get("source_ref") or None,
                    needs_review=bool(record.get("needs_review")),
                )
            )
    return rows


def promote(
    reviewed_path: Path,
    out_path: Path,
    source_document: str,
    source_effective_date: str | None = None,
    ingestion_script_version: str = "phase1",
    skip_empty_fees: bool = False,
) -> int:
    """Stage 2: turn a (possibly hand-edited) reviewed CSV into the final
    reference_data.json shape. Returns the promoted entry count.

    Defaults to keeping every parsed row, including ones flagged needs_review or with no
    price found — they still carry a real code/description, and the flag is preserved on
    the entry so low-confidence rows stay filterable/fixable later without re-ingesting.
    """
    rows = _read_reviewed_csv(Path(reviewed_path))

    codes = []
    seen: set[str] = set()
    for row in rows:
        if skip_empty_fees and not row.fees:
            continue
        if row.code in seen:
            continue
        seen.add(row.code)
        codes.append(
            {
                "code": row.code,
                "description": row.description,
                "category": row.category,
                "keywords": [],
                "unit": row.unit,
                "source_ref": row.source_ref,
                "rule_ids": [],
                "needs_review": row.needs_review,
                "fees": [
                    {
                        "context_label": fee.context_label,
                        "price_cad": fee.price_cad,
                        "percentage": fee.percentage,
                    }
                    for fee in row.fees
                ],
            }
        )

    data = {
        "_meta": {
            "source_document": source_document,
            "source_effective_date": source_effective_date,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "ingestion_script_version": ingestion_script_version,
            "entry_count": len(codes),
        },
        "_pricing_note": (
            "Most codes carry more than one fee — see each code's `fees` list. Time-of-day "
            "and weekend surcharges are separate 'majoration %' codes (see `unit`), not "
            "modeled as automatic multipliers yet."
        ),
        "codes": codes,
    }

    out_path = Path(out_path)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(codes)
