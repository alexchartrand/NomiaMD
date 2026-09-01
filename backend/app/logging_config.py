"""Application-level logging (distinct from app/request_logging.py's per-request access
log): one JSON line per stdout, same container-native reasoning — no file/rotation here,
the orchestrator collects stdout, and docker-compose.yml's `logging:` blocks bound it.

Standard library `logging` only, no new dependency. Configuring the root logger (rather
than just an "app" namespace) means third-party libraries that log through stdlib
logging (sqlalchemy, etc.) get the same JSON formatting for free.
"""

import json
import logging
import sys

_RESERVED_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = {k: v for k, v in record.__dict__.items() if k not in _RESERVED_RECORD_ATTRS}
        payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_LEVEL_COLORS = {
    "DEBUG": "\033[36m",  # cyan
    "INFO": "\033[32m",  # green
    "WARNING": "\033[33m",  # yellow
    "ERROR": "\033[31m",  # red
    "CRITICAL": "\033[41m",  # red background
}
_DIM = "\033[2m"
_RESET = "\033[0m"


class _PrettyFormatter(logging.Formatter):
    """Human-readable, multi-line console formatter for local debugging (try_extraction.py
    and friends) — never used by the real server, which always wants one JSON line per
    record for its container-native log collection (see _JSONFormatter above). Opt in via
    configure_logging(level, pretty=True)."""

    def __init__(self) -> None:
        super().__init__()
        self._use_color = sys.stdout.isatty()

    def _color(self, code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if self._use_color else text

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self._color(_DIM, self.formatTime(record, "%H:%M:%S"))
        level = self._color(_LEVEL_COLORS.get(record.levelname, ""), f"{record.levelname:<8}")
        name = self._color(_DIM, record.name)
        lines = [f"{timestamp} {level} {name}  {record.getMessage()}"]

        extra = {k: v for k, v in record.__dict__.items() if k not in _RESERVED_RECORD_ATTRS}
        for key, value in extra.items():
            lines.append(self._format_field(key, value))
        if record.exc_info:
            lines.append(self.formatException(record.exc_info))
        return "\n".join(lines)

    def _format_field(self, key: str, value: object) -> str:
        if isinstance(value, list) and value and isinstance(value[0], dict):
            items = "\n".join(f"    - {self._format_dict_item(item)}" for item in value)
            return f"  {key} ({len(value)}):\n{items}"
        if isinstance(value, str) and (len(value) > 100 or "\n" in value):
            indented = "\n".join(f"    {line}" for line in value.splitlines())
            return f"  {key}:\n{indented}"
        return f"  {key}: {value}"

    def _format_dict_item(self, item: dict) -> str:
        return " | ".join(str(v) for v in item.values() if v not in (None, "", False))


def configure_logging(level: str, pretty: bool = False) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_PrettyFormatter() if pretty else _JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn configures its own handlers (with propagate=False) on "uvicorn"/
    # "uvicorn.error"/"uvicorn.access" before app.main is even imported, so touching only
    # the root logger wouldn't reach them. Strip their handlers and let "uvicorn"/
    # "uvicorn.error" (startup messages, crash tracebacks) propagate up to the same root
    # handler/formatter. "uvicorn.access" is disabled outright — RequestLoggingMiddleware
    # already logs every request as structured JSON, so uvicorn's own access log would
    # just double every line.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
