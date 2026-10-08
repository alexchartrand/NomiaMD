"""app/benchmark/dataset.py: fixture entries joined to their notes, with filters."""

import json

import pytest

from app.benchmark.dataset import DEFAULT_EVAL_PATH, EvalSetLoader, UnknownCaseError
from app.sample_patients import SamplePatient


def _fixture(tmp_path, entries: list[dict]):
    path = tmp_path / "eval.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def _entry(patient_id: str, **fields) -> dict:
    return {
        "patient_id": patient_id,
        "expected_codes": ["15801"],
        "difficulty": "easy",
        "label_status": "reviewed",
        "physician_context": {"panel_size": 320, "physician_type": "med_fam", "remuneration_type": "a_l_acte"},
        "patient_context": {"age_years": 45, "is_registered": True, "is_vulnerable": False},
        **fields,
    }


def _notes(patient_id: str) -> SamplePatient | None:
    return SamplePatient(id=patient_id, label=patient_id, transcript=f"note {patient_id}", nam=None)


def test_a_case_carries_the_note_the_labels_and_the_billing_context(tmp_path):
    loader = EvalSetLoader(_fixture(tmp_path, [_entry("A")]), notes=_notes)

    [case] = loader.load()

    assert case.transcript == "note A"
    assert case.expected_codes == {"15801"}
    assert case.context.physician.panel_size == 320
    assert case.context.patient.is_registered is True
    assert not case.is_labeled_negative


def test_filters_by_id_label_status_and_difficulty(tmp_path):
    loader = EvalSetLoader(
        _fixture(tmp_path, [_entry("A"), _entry("B", difficulty="hard"), _entry("C", label_status="draft-unverified")]),
        notes=_notes,
    )

    assert [c.patient_id for c in loader.load(patient_ids=["A", "C"])] == ["A", "C"]
    assert [c.patient_id for c in loader.load(difficulties=["hard"])] == ["B"]
    assert [c.patient_id for c in loader.load(label_statuses=["reviewed"], difficulties=["easy"])] == ["A"]


def test_an_unknown_requested_id_fails_loudly(tmp_path):
    loader = EvalSetLoader(_fixture(tmp_path, [_entry("A")]), notes=_notes)

    with pytest.raises(UnknownCaseError, match="NOPE"):
        loader.load(patient_ids=["NOPE"])


def test_empty_expected_codes_is_a_negative_unless_unlabeled(tmp_path):
    loader = EvalSetLoader(
        _fixture(
            tmp_path,
            [_entry("A", expected_codes=[]), _entry("B", expected_codes=[], label_status="needs_physician_label")],
        ),
        notes=_notes,
    )

    a, b = loader.load()

    assert a.is_labeled_negative and not b.is_labeled_negative


def test_the_real_fixture_loads_every_note():
    cases = EvalSetLoader(DEFAULT_EVAL_PATH).load()

    assert len(cases) == 58
    assert all(case.transcript for case in cases)
