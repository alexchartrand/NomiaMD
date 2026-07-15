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


@pytest.fixture(autouse=True)
def no_real_openai_key(monkeypatch):
    """app/main.py loads .env at import time, so a real OPENAI_API_KEY configured there
    (for actually running the app against OpenRouter/OpenAI) would otherwise leak into
    every test process — silently turning on real embedding calls (slow, and network-
    dependent) in tests that never asked for them. Tests that want embeddings "on" opt in
    explicitly by monkeypatching embeddings_enabled/embed_texts themselves; everything else
    should stay hermetic regardless of what's in the developer's local .env."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
