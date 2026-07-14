"""Exercises the real notes_consultation_simulees.md fixture at the repo root — no
mocking needed, this is pure file parsing."""

from fastapi.testclient import TestClient

from app.main import app
from app.sample_patients import get_sample_patient, get_sample_patients


def test_loads_patients_from_real_fixture():
    patients = get_sample_patients()
    assert len(patients) == 5
    assert len({p.id for p in patients}) == 5  # ids are unique
    first = patients[0]
    assert first.id == "URG-2026-04471"
    assert "67" in first.label
    assert "thoracique" in first.label.lower()
    assert "STEMI" in first.transcript


def test_get_sample_patient_by_id():
    patient = get_sample_patient("URG-2026-04471")
    assert patient is not None
    assert "STEMI" in patient.transcript


def test_get_sample_patient_unknown_id_returns_none():
    assert get_sample_patient("does-not-exist") is None


def test_list_patients_endpoint():
    with TestClient(app) as client:
        response = client.get("/patients")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert all(set(entry.keys()) == {"id", "label"} for entry in body)


def test_get_patient_endpoint():
    with TestClient(app) as client:
        response = client.get("/patients/URG-2026-04471")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "URG-2026-04471"
    assert "transcript" in body


def test_get_patient_endpoint_404():
    with TestClient(app) as client:
        response = client.get("/patients/does-not-exist")
    assert response.status_code == 404
