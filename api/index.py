"""Vercel serverless entry: every /api/* route is rewritten here (see
vercel.json) and delegated to the shared host-neutral dispatcher, so local
development and production execute exactly the same code path.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app import dispatch  # noqa: E402


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self, method: str):
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items()}
        client = self.headers.get("X-Forwarded-For",
                                  getattr(self, "client_address", ["unknown"])[0])
        status, response_headers, payload = dispatch(
            method, parsed.path, query=query, headers=headers,
            body_bytes=body, client=str(client))
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def log_message(self, *args):  # keep lambda logs clean
        pass
