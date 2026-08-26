"""Security boundary for the API surface.

- Optional bearer-token authentication for mutating requests (PERSONAL_OS_TOKEN).
- Per-client sliding-window rate limiting for mutations.
- Payload size caps, JSON validation and kind/relation allow-lists enforced
  upstream in the dispatcher.
- No secret is ever written to the repository or echoed back through the API;
  integration status endpoints report *which* env var is missing, never values.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

from .util import iso

MAX_BODY_BYTES = 100_000
RATE_WINDOW_SECONDS = 60
RATE_LIMIT_MUTATIONS = 60

class RateLimiter:
    def __init__(self, db):
        self.db = db
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, client_key: str, *, limit: int = RATE_LIMIT_MUTATIONS,
              window: float = RATE_WINDOW_SECONDS) -> dict:
        now = time.monotonic()
        start, count = self._buckets.get(client_key, (now, 0))
        if now - start > window:
            start, count = now, 0
        count += 1
        self._buckets[client_key] = (start, count)
        allowed = count <= limit
        return {"allowed": allowed, "count": count, "limit": limit,
                "retry_after": 0 if allowed else int(window - (now - start))}

class Authenticator:
    """If PERSONAL_OS_TOKEN is set, mutations require `Authorization: Bearer`.
    Read endpoints stay open for the single-user owner experience. Never log or
    return the token; comparisons are constant-time."""

    def __init__(self):
        self._token = os.environ.get("PERSONAL_OS_TOKEN")

    @property
    def enforced(self) -> bool:
        return bool(self._token)

    def check(self, headers: dict) -> dict:
        if not self._token:
            return {"ok": True, "mode": "open",
                    "note": "set PERSONAL_OS_TOKEN to require authentication on mutations"}
        auth = ""
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth = value
        provided = auth.removeprefix("Bearer ").strip()
        ok = hmac.compare_digest(hashlib.sha256(provided.encode()).digest(),
                                 hashlib.sha256(self._token.encode()).digest())
        return {"ok": ok, "mode": "enforced",
                "error": None if ok else "invalid or missing bearer token"}

def scrub(text: str) -> str:
    """Defensive helper: never let env-looking secret values leak into payloads."""
    if not text:
        return text
    for marker in ("token=", "secret=", "apikey=", "api_key=", "password=", "bearer "):
        lowered = text.lower()
        if marker in lowered:
            idx = lowered.index(marker)
            head, tail = text[:idx + len(marker)], text[idx + len(marker):]
            end = next((i for i, ch in enumerate(tail) if ch in " ,;\"'"), len(tail))
            text = head + "***" + tail[end:]
    return text

def audit_security_event(db, kind: str, detail: dict):
    db.execute("INSERT INTO audit(id,actor,action,permission,risk,approved,result,created_at)"
               " VALUES(?,?,?,?,?,?,?,?)",
               (f"sec_{int(time.time()*1000)}", "security", kind, "READ_DATA", 0, 0,
                __import__("json").dumps(detail), iso()))
