"""Exercises the real consultations/ fixture at the repo root — no mocking needed,
this is pure file parsing."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.sample_patients import get_sample_patient, get_sample_patients


def test_loads_patients_from_real_fixture():
    patients = get_sample_patients()
    assert len(patients) == 58
    assert len({p.id for p in patients}) == 58  # ids are unique
    stemi = next(p for p in patients if p.id == "URG-2026-04471")
    assert "67" in stemi.label
    assert "thoracique" in stemi.label.lower()
    assert "STEMI" in stemi.transcript


def test_get_sample_patient_by_id():
    patient = get_sample_patient("URG-2026-04471")
    assert patient is not None
    assert "STEMI" in patient.transcript


def test_get_sample_patient_unknown_id_returns_none():
    assert get_sample_patient("does-not-exist") is None


def test_nam_header_line_does_not_disturb_id_or_label_parsing():
    # id still comes from **Dossier :**, not from the new **NAM :** line that now sits
    # between **Patient :** and **Dossier :** in every fixture note.
    stemi = get_sample_patient("URG-2026-04471")
    assert stemi is not None
    assert stemi.id == "URG-2026-04471"
    assert "67" in stemi.label
    assert "**NAM :** GAGR59071301" in stemi.transcript


def test_nam_is_parsed_and_normalized():
    stemi = get_sample_patient("URG-2026-04471")
    assert stemi is not None
    assert stemi.nam == "GAGR59071301"


def test_get_patient_endpoint_includes_nam():
    with TestClient(app) as client:
        response = client.get("/sample-patients/URG-2026-04471")
    assert response.status_code == 200
    assert response.json()["nam"] == "GAGR59071301"


def test_list_patients_endpoint():
    with TestClient(app) as client:
        response = client.get("/sample-patients")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 58
    assert all(set(entry.keys()) == {"id", "label"} for entry in body)


def test_get_patient_endpoint():
    with TestClient(app) as client:
        response = client.get("/sample-patients/URG-2026-04471")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "URG-2026-04471"
    assert "transcript" in body


def test_get_patient_endpoint_404():
    with TestClient(app) as client:
        response = client.get("/sample-patients/does-not-exist")
    assert response.status_code == 404


def test_eval_fixture_entries_point_at_real_notes():
    # scripts/eval_extraction.py resolves each entry's patient_id against these notes and
    # silently skips the ones it can't find — a renamed dossier would quietly shrink the eval.
    fixture = Path(__file__).parent / "fixtures" / "eval_billing_codes.jsonl"
    entries = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]

    assert len({entry["patient_id"] for entry in entries}) == len(entries)
    for entry in entries:
        assert get_sample_patient(entry["patient_id"]) is not None, entry["patient_id"]
        assert all(re.fullmatch(r"\d{5}", code) for code in entry["expected_codes"]), entry["patient_id"]
        assert entry["label_status"] in {"draft-unverified", "to_review", "needs_physician_label"}
        assert ("review_reason" in entry) == (entry["label_status"] == "to_review"), entry["patient_id"]
