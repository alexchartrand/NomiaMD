"""Tests for vector_store.py — IVectorStore's ABC contract, and LanceVectorStore's wiring.
LanceDBVectorStore is swapped for a fake at the module level so no on-disk Lance dataset is
ever created. Mirrors ramq-ingestion's tests/test_lancedb_vector_store.py."""

import pytest

import app.ramq_codes.vector_store as vector_store_module
from app.ramq_codes.vector_store import IVectorStore


class _FakeLanceDBVectorStore:
    def __init__(self, uri, table_name, flat_metadata):
        self.uri = uri
        self.table_name = table_name
        self.flat_metadata = flat_metadata


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        IVectorStore()


def test_get_vector_store_builds_lancedb_store_at_persist_dir(monkeypatch):
    monkeypatch.setattr(vector_store_module, "LanceDBVectorStore", _FakeLanceDBVectorStore)

    store = vector_store_module.LanceVectorStore(persist_dir="/tmp/wherever")
    vector_store = store.get_vector_store("codes")

    assert isinstance(vector_store, _FakeLanceDBVectorStore)
    assert vector_store.uri == "/tmp/wherever"
    assert vector_store.table_name == "codes"
    # RAMQ code metadata carries nested fields (when_to_use, rules, fees) —
    # flat_metadata=True (llama_index's default) rejects any non-str/int/float/None value.
    assert vector_store.flat_metadata is False


def test_persist_dir_is_required():
    with pytest.raises(TypeError):
        vector_store_module.LanceVectorStore()


def test_table_name_is_required(monkeypatch):
    monkeypatch.setattr(vector_store_module, "LanceDBVectorStore", _FakeLanceDBVectorStore)

    store = vector_store_module.LanceVectorStore(persist_dir="/tmp/wherever")

    with pytest.raises(TypeError):
        store.get_vector_store()


def test_same_persist_dir_can_vend_different_tables(monkeypatch):
    monkeypatch.setattr(vector_store_module, "LanceDBVectorStore", _FakeLanceDBVectorStore)

    store = vector_store_module.LanceVectorStore(persist_dir="/tmp/wherever")

    codes_store = store.get_vector_store("codes")
    other_store = store.get_vector_store("manuel-omnipraticiens")

    assert codes_store.table_name == "codes"
    assert other_store.table_name == "manuel-omnipraticiens"
    assert codes_store.uri == other_store.uri == "/tmp/wherever"
