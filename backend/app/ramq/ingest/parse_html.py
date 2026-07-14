"""Parses a browser-saved export of the RAMQ manual (Save As → Webpage, Complete) into
RawCodeRow records.

Real layout, established during a discovery pass against the actual export (see the plan
this was built from — not guessed blind):
- Section headings are `<h2>`/`<h3>` tags, often numbered ("2.1 Consultations").
- Most fee rows are a `<tr>` with: a spacer `<td>`, a `<td>` containing the bare code in
  `<strong>` (4-5 digits), a description `<td>` (one or more `<p>` lines), and a price
  `<td>` (one or more right-aligned `<p>` lines, French decimal comma, e.g. "85,75").
- A meaningful fraction of codes have two prices, not one (e.g. "en cabinet" vs. "en
  CLSC/GMF-U") — the description cell often carries one shared leading line followed by
  one variant-context line per price, which this parser pairs positionally.
- Some rows are pure grouping labels (a bold-only cell spanning the code+description
  columns, e.g. "Visite de prise en charge") that provide context for the rows that follow
  them within the same table, rather than being a code themselves.
- "Majoration" rows (time-of-day/weekend surcharges) are a distinct 6-column shape with a
  percentage instead of a dollar price.
- `class="avisGauche"`/`"avisDroit"` rows are AVIS notices referencing codes in passing,
  not fee definitions — excluded.
"""

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.ramq.ingest.models import RawCodeRow, RawFeeVariant

_CODE_RE = re.compile(r"^\d{4,5}$")
_PERCENT_RE = re.compile(r"^([\d.,]+)\s*%$")
_MAX_HEADER_LABEL_LEN = 150


def _text(el: Tag) -> str:
    return el.get_text(" ", strip=True).replace("\xa0", " ").strip()


def _parse_price(text: str) -> float | None:
    cleaned = text.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_avis_row(cells: list[Tag]) -> bool:
    return any("avisGauche" in (c.get("class") or []) or "avisDroit" in (c.get("class") or []) for c in cells)


def _find_code_cell(cells: list[Tag]) -> tuple[int, str] | None:
    for i, cell in enumerate(cells):
        text = _text(cell)
        if _CODE_RE.fullmatch(text):
            return i, text
    return None


def _find_percent_cell(cells: list[Tag], skip: int) -> tuple[int, float] | None:
    for i, cell in enumerate(cells):
        if i == skip:
            continue
        m = _PERCENT_RE.match(_text(cell))
        if m:
            pct = _parse_price(m.group(1))
            if pct is not None:
                return i, pct
    return None


def _paragraph_lines(cell: Tag) -> list[str]:
    return [t for p in cell.find_all("p") for t in [_text(p)] if t]


def _find_price_cell(cells: list[Tag], start_idx: int) -> Tag:
    """The price cell isn't reliably the last `<td>` — some tables carry a trailing empty
    5th column. Scan from the end for the rightmost cell that actually parses as price(s);
    fall back to the last cell (preserving today's "no price found" flagging) if none do.
    """
    for cell in reversed(cells[start_idx:]):
        texts = _paragraph_lines(cell)
        if any(_parse_price(t) is not None for t in texts):
            return cell
    return cells[-1]


def _build_fee_row(
    code: str,
    cells: list[Tag],
    code_idx: int,
    category: str,
    header_stack: list[str],
    row_id: str | None,
    raw_text: str,
) -> RawCodeRow | None:
    if code_idx + 1 >= len(cells):
        return None
    description_cell = cells[code_idx + 1]
    price_cell = _find_price_cell(cells, code_idx + 1)

    desc_lines = _paragraph_lines(description_cell)
    price_texts = _paragraph_lines(price_cell)
    price_lines = [p for p in (_parse_price(t) for t in price_texts) if p is not None]

    needs_review = False
    if len(price_lines) == 1:
        # A single price is never "one variant among several" — the whole description
        # cell belongs in the description, not split off as a fee-variant label.
        shared_header: list[str] = desc_lines
        fees = [RawFeeVariant(context_label="", price_cad=price_lines[0])]
    elif len(desc_lines) == len(price_lines) and price_lines:
        shared_header = []
        variant_lines = desc_lines
        fees = [
            RawFeeVariant(context_label=d, price_cad=p)
            for d, p in zip(variant_lines, price_lines)
        ]
    elif len(desc_lines) > len(price_lines) and price_lines:
        split = len(desc_lines) - len(price_lines)
        shared_header = desc_lines[:split]
        variant_lines = desc_lines[split:]
        fees = [
            RawFeeVariant(context_label=d, price_cad=p)
            for d, p in zip(variant_lines, price_lines)
        ]
    else:
        shared_header = desc_lines
        fees = [
            RawFeeVariant(context_label=d, price_cad=p)
            for d, p in zip(desc_lines, price_lines)
        ]
        needs_review = True

    description = " — ".join(part for part in (*header_stack, *shared_header) if part)
    return RawCodeRow(
        code=code,
        description=description or code,
        category=category,
        fees=fees,
        source_ref=row_id,
        raw_row_text=raw_text,
        needs_review=needs_review or not fees,
    )


def _build_majoration_row(
    code: str,
    cells: list[Tag],
    code_idx: int,
    percent_idx: int,
    percentage: float,
    category: str,
    row_id: str | None,
    raw_text: str,
) -> RawCodeRow:
    context_bits = [_text(cells[i]) for i in range(code_idx) if _text(cells[i])]
    note_bits = [
        _text(cells[i]) for i in range(percent_idx + 1, len(cells)) if _text(cells[i])
    ]
    context_label = ", ".join(context_bits)
    description = ", ".join([*context_bits, *note_bits]) or code
    return RawCodeRow(
        code=code,
        description=description,
        category=category,
        fees=[RawFeeVariant(context_label=context_label, percentage=percentage)],
        unit="majoration %",
        source_ref=row_id,
        raw_row_text=raw_text,
        needs_review=False,
    )


def parse(html_path) -> list[RawCodeRow]:
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")

    rows: list[RawCodeRow] = []
    category = ""
    # Each entry: [label, emitted_since_push]. Grouping-label rows (e.g. "Visite de prise
    # en charge") have no depth/indentation marker in the source markup to distinguish "this
    # nests under the current header" from "this replaces the current header as a sibling"
    # — both look identical. Heuristic: once a header has produced at least one code row, the
    # next header at a plain append point is presumed to replace it (a sibling), not nest
    # under it; before that, it's presumed a deeper nesting. This resolves the common
    # 2-level "grouping — variant" pattern correctly but can occasionally leave a stale
    # ancestor label in place after a 3+-level sibling transition — rows produced right
    # after a replacement are flagged needs_review so this is caught in the human review
    # pass rather than trusted silently.
    header_stack: list[list] = []
    stack_replaced = False
    current_table = None

    for el in soup.find_all(["h2", "h3", "tr"]):
        if el.name in ("h2", "h3"):
            text = _text(el)
            if text:
                category = text
            continue

        tr = el
        parent_table = tr.find_parent("table")
        if parent_table is not current_table:
            current_table = parent_table
            header_stack = []
            stack_replaced = False

        cells = tr.find_all("td", recursive=False)
        if not cells or _is_avis_row(cells):
            continue

        raw_text = str(tr)
        code_match = _find_code_cell(cells)

        if code_match is None:
            price_cell = _find_price_cell(cells, 0)
            price_texts = _paragraph_lines(price_cell)
            prices = [p for p in (_parse_price(t) for t in price_texts) if p is not None]
            # Real codes rarely carry more than 2-3 context-dependent prices. A run of
            # many continuation rows in a row usually means a table shape this parser
            # doesn't understand (e.g. a duration/multiplier grid) is being misattributed
            # to the last recognized code rather than genuinely extending it — stop
            # merging past a small cap rather than silently corrupting that code's fees.
            if prices and rows and len(rows[-1].fees) < 4:
                # A continuation row: no code of its own, but a real price somewhere in
                # it — extends the most recently emitted code with an additional
                # context-specific price rather than being a grouping header (headers
                # never carry a price) or belonging to a new code.
                desc_bits = [
                    t for cell in cells if cell is not price_cell for t in _paragraph_lines(cell)
                ]
                context_label = " ".join(desc_bits).strip()
                if len(desc_bits) == len(prices) and len(prices) > 1:
                    for label, price in zip(desc_bits, prices):
                        rows[-1].fees.append(RawFeeVariant(context_label=label, price_cad=price))
                else:
                    for price in prices:
                        rows[-1].fees.append(RawFeeVariant(context_label=context_label, price_cad=price))
                rows[-1].needs_review = True
                continue

            # A grouping-label row (e.g. "Visite de prise en charge") that provides
            # context for the code rows following it in this table.
            candidate = next((c for c in cells if c.has_attr("colspan")), None)
            if candidate is not None:
                text = _text(candidate)
                if text and len(text) <= _MAX_HEADER_LABEL_LEN:
                    if header_stack and header_stack[-1][1]:
                        header_stack.pop()
                        stack_replaced = True
                    header_stack.append([text, False])
            continue

        code_idx, code = code_match
        row_id = tr.get("id")
        for entry in header_stack:
            entry[1] = True
        labels = [entry[0] for entry in header_stack]
        was_replaced, stack_replaced = stack_replaced, False

        percent_match = _find_percent_cell(cells, skip=code_idx)
        if percent_match is not None:
            percent_idx, percentage = percent_match
            row = _build_majoration_row(
                code, cells, code_idx, percent_idx, percentage, category, row_id, raw_text
            )
            row.needs_review = row.needs_review or was_replaced
            rows.append(row)
            continue

        fee_row = _build_fee_row(code, cells, code_idx, category, labels, row_id, raw_text)
        if fee_row is not None:
            fee_row.needs_review = fee_row.needs_review or was_replaced
            rows.append(fee_row)

    return rows
