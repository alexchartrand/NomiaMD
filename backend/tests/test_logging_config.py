"""Tests for app/logging_config.py: the JSON line format configure_logging() wires onto
the root logger, and that the configured level actually filters records."""

import json
import logging

import pytest

from app.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    # configure_logging() mutates the root logger's handlers/level globally — restore
    # whatever app.main's own startup call left in place so later tests aren't affected.
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_configure_logging_emits_one_json_line_per_record(capsys):
    configure_logging("INFO")
    logger = logging.getLogger("test.logging_config")

    logger.warning("something happened", extra={"foo": "bar"})

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "test.logging_config"
    assert payload["message"] == "something happened"
    assert payload["foo"] == "bar"


def test_configure_logging_filters_below_configured_level(capsys):
    configure_logging("WARNING")
    logger = logging.getLogger("test.logging_config")

    logger.info("should not appear")

    assert capsys.readouterr().out.strip() == ""
