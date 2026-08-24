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


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JSONFormatter())

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
