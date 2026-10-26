"""app/benchmark/store.py: records round-trip, resume detection, baselines."""

import pytest

from app.benchmark.records import RetrievalRecord
from app.benchmark.store import RunNotFoundError, RunStore
from tests.benchmark_helpers import call, manifest, retrieval_record


def test_a_record_round_trips_with_its_calls(tmp_path):
    run = RunStore(tmp_path).create("base")
    record = retrieval_record("CLI-1", [("A", "Visites")], calls=[call(input_tokens=42)])

    run.write("retrieval", record)

    assert run.has("retrieval", "CLI-1") and not run.has("summary", "CLI-1")
    assert run.read("retrieval", "CLI-1", RetrievalRecord) == record
    assert run.read("retrieval", "CLI-2", RetrievalRecord) is None
    assert run.patient_ids("retrieval") == ["CLI-1"]


def test_no_temporary_file_is_left_behind(tmp_path):
    run = RunStore(tmp_path).create("base")

    run.write("retrieval", retrieval_record("CLI-1", []))

    assert [p.name for p in (run.path / "notes" / "CLI-1").iterdir()] == ["retrieval.json"]


def test_a_run_exists_once_it_has_a_manifest(tmp_path):
    store = RunStore(tmp_path)
    run = store.create("base")
    assert not store.exists("base")

    run.write_manifest(manifest("base"))

    assert store.exists("base")
    assert store.open("base").read_manifest().name == "base"


def test_promote_copies_a_run_into_baselines_where_open_still_finds_it(tmp_path):
    store = RunStore(tmp_path)
    run = store.create("base")
    run.write_manifest(manifest("base"))
    run.write("retrieval", retrieval_record("CLI-1", []))

    baseline = store.promote("base", "mistral-2026-10")

    assert baseline.path == tmp_path / "baselines" / "mistral-2026-10"
    assert store.open("mistral-2026-10").has("retrieval", "CLI-1")
    with pytest.raises(FileExistsError):
        store.promote("base", "mistral-2026-10")


def test_opening_an_unknown_run_fails(tmp_path):
    with pytest.raises(RunNotFoundError, match="nope"):
        RunStore(tmp_path).open("nope")
