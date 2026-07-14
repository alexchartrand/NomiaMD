from pathlib import Path

import pytest

from app.ramq import reference as reference_module

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


@pytest.fixture(autouse=True)
def small_reference_table(monkeypatch):
    """Points the RAMQ reference table at a tiny, stable fixture rather than the real
    (large, frequently-regenerated) reference_data.json, so tests don't depend on its
    exact size/content — see reference.py's load() for why monkeypatching the module
    attribute (rather than passing path=...) works here."""
    monkeypatch.setattr(reference_module, "REFERENCE_PATH", SMALL_REFERENCE_PATH)
    reference_module.get_reference_table.cache_clear()
    yield
    reference_module.get_reference_table.cache_clear()
