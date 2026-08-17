"""One structured JSON line per request to stdout — container-native (no file/rotation
needed, the orchestrator collects stdout), and captures what uvicorn's default access log
doesn't: a request ID to correlate with error reports, and latency. Useful given /extract
and /query (app/main.py) cost real money per call.
"""

import json
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        print(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "client": request.client.host if request.client else None,
        }))

        response.headers["X-Request-ID"] = request_id
        return response
