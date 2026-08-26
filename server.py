#!/usr/bin/env python3
"""myos Personal OS — local development server.

Serves the static frontend from the repository root and the full JSON API
through the same host-neutral dispatcher the Vercel function uses. Reads:
  PORT             default 8000
  PERSONAL_OS_DB   sqlite path (default ./personal_os.sqlite3)
  PERSONAL_OS_TOKEN  optional bearer token protecting mutations locally too
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api_app import dispatch

ROOT = Path(__file__).parent

STATIC_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Content-Security-Policy",
     "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
     "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
     "frame-ancestors 'none'; base-uri 'self'"),
]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        for key, value in STATIC_HEADERS:
            self.send_header(key, value)
        super().end_headers()

    # -------------------------------------------------------------- API
    def _api(self, method: str) -> bool:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return False
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items()}
        status, response_headers, payload = dispatch(
            method, parsed.path, query=query, headers=headers,
            body_bytes=body, client=self.client_address[0])
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)
        return True

    def do_GET(self):
        if not self._api("GET"):
            super().do_GET()

    def do_POST(self):
        if not self._api("POST"):
            self.send_error(404)

    def do_PATCH(self):
        if not self._api("PATCH"):
            self.send_error(404)

    def do_DELETE(self):
        if not self._api("DELETE"):
            self.send_error(404)

    def do_OPTIONS(self):
        self._api("OPTIONS")

    def log_message(self, fmt, *args):
        if "/api/" not in (args[0] if args else ""):
            return  # quiet static serving logs
        super().log_message(fmt, *args)


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"myos Personal OS → http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
