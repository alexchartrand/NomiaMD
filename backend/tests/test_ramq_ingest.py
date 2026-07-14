"""Tests for the HTML ingestion parser against small hand-written fixtures mirroring the
real manual's structure (established via a discovery pass against the actual export — see
app/ramq/ingest/parse_html.py's docstring), plus the extract_raw/promote round trip.

Not tested against the real ~3.7MB export — that's exercised manually via
scripts/ingest_ramq_manual.py and validated by test_ramq_reference_data.py's regression
checks on the promoted output.
"""

from pathlib import Path

from app.ramq.ingest.build_reference import extract_raw, promote
from app.ramq.ingest.parse_html import parse

FIXTURES = Path(__file__).parent / "fixtures"


def _write_html(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sample.html"
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    return path


def test_parses_single_price_code(tmp_path):
    html = """
    <h2>B — Consultation, examen et visite</h2>
    <table><tbody>
    <tr id="1"><td><br></td><td><p><strong>08579</strong></p></td>
    <td><p>Révision, avec rapport écrit, d'un examen de résonance magnétique</p></td>
    <td><p align="right">17,80</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    assert len(rows) == 1
    row = rows[0]
    assert row.code == "08579"
    assert "résonance magnétique" in row.description
    assert row.category == "B — Consultation, examen et visite"
    assert len(row.fees) == 1
    assert row.fees[0].price_cad == 17.8
    assert row.fees[0].context_label == ""
    assert not row.needs_review


def test_parses_multi_price_code_with_shared_header(tmp_path):
    html = """
    <h2>B — Consultation, examen et visite</h2>
    <table><tbody>
    <tr id="1"><td><br></td><td colspan="2"><p><strong>Visite de prise en charge</strong></p></td><td><br></td></tr>
    <tr id="2"><td><br></td><td><p><strong>15801</strong></p></td>
    <td><p>Clientèle inscrite de moins de 500 patients</p>
    <p>En cabinet ou à domicile</p>
    <p>En CLSC ou en GMF-U</p></td>
    <td><p align="right">85,75</p><p align="right">64,50</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    assert len(rows) == 1
    row = rows[0]
    assert row.code == "15801"
    assert "Visite de prise en charge" in row.description
    assert "Clientèle inscrite de moins de 500 patients" in row.description
    assert [f.price_cad for f in row.fees] == [85.75, 64.50]
    assert row.fees[0].context_label == "En cabinet ou à domicile"
    assert row.fees[1].context_label == "En CLSC ou en GMF-U"


def test_header_replacement_flags_needs_review(tmp_path):
    html = """
    <h2>B — Consultation, examen et visite</h2>
    <table><tbody>
    <tr id="1"><td><br></td><td colspan="2"><p><strong>Patient non vulnérable inscrit</strong></p></td><td><br></td></tr>
    <tr id="2"><td><br></td><td colspan="2"><p><strong>Visite de prise en charge</strong></p></td><td><br></td></tr>
    <tr id="3"><td><br></td><td><p><strong>15801</strong></p></td><td><p>Clientèle A</p></td><td><p align="right">85,75</p></td></tr>
    <tr id="4"><td><br></td><td colspan="2"><p><strong>Visite de suivi</strong></p></td><td><br></td></tr>
    <tr id="5"><td><br></td><td><p><strong>15803</strong></p></td><td><p>Clientèle A</p></td><td><p align="right">42,85</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    by_code = {r.code: r for r in rows}
    # "Visite de prise en charge" stays in scope for 15801 (first header still active).
    assert "Patient non vulnérable inscrit" in by_code["15801"].description
    assert "Visite de prise en charge" in by_code["15801"].description
    assert not by_code["15801"].needs_review
    # "Visite de suivi" replaces its sibling for 15803 — flagged since the replacement is
    # a heuristic guess, not a structural certainty (see parse_html.py's docstring).
    assert "Patient non vulnérable inscrit" in by_code["15803"].description
    assert "Visite de suivi" in by_code["15803"].description
    assert "Visite de prise en charge" not in by_code["15803"].description
    assert by_code["15803"].needs_review


def test_majoration_row_parsed_as_percentage(tmp_path):
    html = """
    <h2>1.4 Rémunération pour la garde sur place</h2>
    <table><tbody>
    <tr id="1"><td><p align="center">0 h à 8 h</p></td><td><p align="center">en semaine</p></td>
    <td><p align="center">1er</p></td><td><p align="center"><strong>09998</strong></p></td>
    <td><p align="center">101 %</p></td><td><p align="center">non divisible</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    assert len(rows) == 1
    row = rows[0]
    assert row.code == "09998"
    assert row.unit == "majoration %"
    assert row.fees[0].percentage == 101.0
    assert row.fees[0].price_cad is None


def test_continuation_row_extends_previous_code(tmp_path):
    html = """
    <h2>Psychothérapie</h2>
    <table><tbody>
    <tr id="1"><td><br></td><td><p><strong>08862</strong></p></td>
    <td><p>Psychothérapie individuelle, première période de trente minutes</p></td>
    <td><p align="right"></p></td></tr>
    <tr id="2"><td><br></td><td><br></td>
    <td><p>En établissement sauf en CLSC et en GMF-U</p></td>
    <td><p align="right">49,75</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    assert len(rows) == 1
    row = rows[0]
    assert row.code == "08862"
    assert len(row.fees) == 1
    assert row.fees[0].price_cad == 49.75
    assert "établissement" in row.fees[0].context_label
    assert row.needs_review  # heuristic continuation attribution, flagged for a spot check


def test_avis_notice_row_excluded(tmp_path):
    html = """
    <h2>B</h2>
    <table><tbody>
    <tr><td class="avisGauche"><p>AVIS</p></td>
    <td class="avisDroit"><p>Voir le code 15801 pour plus de détails.</p></td></tr>
    <tr id="1"><td><br></td><td><p><strong>08579</strong></p></td>
    <td><p>Un acte</p></td><td><p align="right">17,80</p></td></tr>
    </tbody></table>
    """
    rows = parse(_write_html(tmp_path, html))
    assert [r.code for r in rows] == ["08579"]


def test_extract_raw_and_promote_round_trip(tmp_path):
    html = """
    <h2>B — Consultation, examen et visite</h2>
    <table><tbody>
    <tr id="1"><td><br></td><td><p><strong>08579</strong></p></td>
    <td><p>Un acte quelconque</p></td><td><p align="right">17,80</p></td></tr>
    </tbody></table>
    """
    source = _write_html(tmp_path, html)
    raw_csv = tmp_path / "raw.csv"
    count = extract_raw(source, raw_csv)
    assert count == 1
    assert raw_csv.exists()

    out_json = tmp_path / "reference_data.json"
    promoted = promote(raw_csv, out_json, source_document="Test manual")
    assert promoted == 1

    import json

    data = json.loads(out_json.read_text())
    assert data["_meta"]["source_document"] == "Test manual"
    assert data["_meta"]["entry_count"] == 1
    assert data["codes"][0]["code"] == "08579"
    assert data["codes"][0]["fees"][0]["price_cad"] == 17.8
