#!/usr/bin/env python3
"""T115 — local Alertmanager webhook receiver for integration tests.

Listens on `:9099`. Routes:

- ``POST /webhook`` — captures an Alertmanager webhook envelope into an
  in-memory buffer. Alertmanager posts its envelope shape (the JSON contains
  ``alerts: [...]`` with ``labels`` and ``annotations`` per alert).
- ``GET  /captured`` — returns the captured envelopes as a JSON list. Does
  not drain.
- ``DELETE /captured`` — returns the captured envelopes as a JSON list AND
  drains the buffer. Used by the T107 integration test between runs.
- ``GET  /healthz`` — readiness probe.

The receiver is intentionally minimal: stdlib only (``http.server``) so the
Compose service starts in <100ms and adds no Python-deps surface. The buffer
is bounded at 1000 envelopes to prevent unbounded growth in a long-running
session; entries beyond that overwrite the oldest (FIFO).
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_BUFFER_SIZE = 1000
_buffer: deque[dict[str, Any]] = deque(maxlen=_BUFFER_SIZE)
_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    server_version = "collectmind-local-webhook/0.1"

    def _write_json(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/captured":
            with _lock:
                snapshot = list(_buffer)
            self._write_json(HTTPStatus.OK, snapshot)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})

    def do_DELETE(self) -> None:
        if self.path == "/captured":
            with _lock:
                snapshot = list(_buffer)
                _buffer.clear()
            self._write_json(HTTPStatus.OK, snapshot)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            envelope = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json", "detail": str(exc)})
            return
        with _lock:
            _buffer.append(envelope)
        self._write_json(HTTPStatus.OK, {"received": 1})

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet by default; flip to True for verbose debugging.
        if os.environ.get("LOCAL_WEBHOOK_VERBOSE"):
            super().log_message(format, *args)


def main() -> int:
    host = os.environ.get("LOCAL_WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("LOCAL_WEBHOOK_PORT", "9099"))
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"local-webhook listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
