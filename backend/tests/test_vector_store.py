"""Tests for vector_store.py — ICodeTableReader's ABC contract, and LanceCodeTableReader's
wiring. lancedb.connect is swapped for a fake at the module level so no on-disk Lance
dataset is ever created/opened. Mirrors ramq-ingestion's tests/test_code_table_writer.py's
counterpart on the write side."""

import pytest

import app.ramq_codes.vector_store as vector_store_module
from app.ramq_codes.vector_store import ICodeTableReader


class _FakeTable:
    def __init__(self, uri, table_name):
        self.uri = uri
        self.table_name = table_name


class _FakeConnection:
    def __init__(self, uri):
        self.uri = uri

    def open_table(self, table_name):
        return _FakeTable(self.uri, table_name)


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        ICodeTableReader()


def test_open_table_connects_at_persist_dir_and_opens_table(monkeypatch):
    monkeypatch.setattr(vector_store_module.lancedb, "connect", _FakeConnection)

    reader = vector_store_module.LanceCodeTableReader(persist_dir="/tmp/wherever")
    table = reader.open_table("codes")

    assert isinstance(table, _FakeTable)
    assert table.uri == "/tmp/wherever"
    assert table.table_name == "codes"


def test_persist_dir_is_required():
    with pytest.raises(TypeError):
        vector_store_module.LanceCodeTableReader()


def test_table_name_is_required(monkeypatch):
    monkeypatch.setattr(vector_store_module.lancedb, "connect", _FakeConnection)

    reader = vector_store_module.LanceCodeTableReader(persist_dir="/tmp/wherever")

    with pytest.raises(TypeError):
        reader.open_table()


def test_same_persist_dir_can_open_different_tables(monkeypatch):
    monkeypatch.setattr(vector_store_module.lancedb, "connect", _FakeConnection)

    reader = vector_store_module.LanceCodeTableReader(persist_dir="/tmp/wherever")

    codes_table = reader.open_table("codes")
    other_table = reader.open_table("specialist_codes")

    assert codes_table.table_name == "codes"
    assert other_table.table_name == "specialist_codes"
    assert codes_table.uri == other_table.uri == "/tmp/wherever"
