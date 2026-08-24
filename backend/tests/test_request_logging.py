"""Tests for app/request_logging.py's RequestLoggingMiddleware: the per-request JSON
access-log line (method/path/status/duration/request_id), and its handling of an
unhandled exception — logged with the same request_id before re-raising so Starlette's
normal error handling still produces the response."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.request_logging import RequestLoggingMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    return app


def test_successful_request_logs_json_line_and_sets_request_id_header(capsys):
    with TestClient(_make_app()) as client:
        response = client.get("/ok")

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]

    logged = json.loads(capsys.readouterr().out.strip())
    assert logged["request_id"] == request_id
    assert logged["method"] == "GET"
    assert logged["path"] == "/ok"
    assert logged["status"] == 200


def test_unhandled_exception_is_logged_with_request_id_and_still_returns_500(capsys, caplog):
    with caplog.at_level("ERROR", logger="app.request_logging"):
        with TestClient(_make_app(), raise_server_exceptions=False) as client:
            response = client.get("/boom")

    assert response.status_code == 500

    [record] = caplog.records
    assert record.levelname == "ERROR"
    assert record.exc_info is not None
    assert record.path == "/boom"

    logged = json.loads(capsys.readouterr().out.strip())
    assert logged["status"] == 500
    assert logged["request_id"] == record.request_id
