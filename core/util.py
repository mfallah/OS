"""Shared utilities: time, ids, json helpers. Dependency-free."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

UTC = timezone.utc

def iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

def today() -> str:
    return datetime.now(UTC).date().isoformat()

def uid(prefix: str = "ent") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

def loads(text: str):
    return json.loads(text)

def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))

def words(text: str):
    """Lowercase word tokens with stopwords removed; used by scoring/search."""
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with",
            "my", "me", "i", "is", "are", "was", "be", "do", "does", "what", "how"}
    return [w for w in re.split(r"[^a-zA-Z\u0600-\u06FF0-9]+", text.lower())
            if len(w) > 2 and w not in stop]

def title_of(entity: dict) -> str:
    return str(entity.get("title") or entity.get("name") or entity.get("question")
               or entity.get("content", "")[:60] or entity.get("id", "untitled"))
