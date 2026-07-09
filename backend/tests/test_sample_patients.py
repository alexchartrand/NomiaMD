"""Exercises the real train.jsonl fixture at the repo root — no mocking needed, this is
pure file parsing."""

from fastapi.testclient import TestClient

from app.main import app
from app.sample_patients import get_sample_patient, get_sample_patients


def test_loads_patients_from_real_fixture():
    patients = get_sample_patients()
    assert len(patients) == 50
    assert len({p.id for p in patients}) == 50  # ids are unique
    first = patients[0]
    assert first.id == "consult_000000"
    assert "46F" in first.label
    assert "blood pressure" in first.label.lower()
    assert "patient:" in first.transcript
    assert "doctor:" in first.transcript


def test_get_sample_patient_by_id():
    patient = get_sample_patient("consult_000000")
    assert patient is not None
    assert patient.transcript.startswith("patient:")


def test_get_sample_patient_unknown_id_returns_none():
    assert get_sample_patient("does-not-exist") is None


def test_list_patients_endpoint():
    with TestClient(app) as client:
        response = client.get("/patients")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 50
    assert all(set(entry.keys()) == {"id", "label"} for entry in body)


def test_get_patient_endpoint():
    with TestClient(app) as client:
        response = client.get("/patients/consult_000000")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "consult_000000"
    assert "transcript" in body


def test_get_patient_endpoint_404():
    with TestClient(app) as client:
        response = client.get("/patients/does-not-exist")
    assert response.status_code == 404
