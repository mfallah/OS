"""Event system: durable, idempotent domain events with in-process subscribers.

The bus is the nervous system of the OS: every mutation emits an event and
subscribers (insights, projectors, notification rules) react without coupling
the writer to downstream concerns.
"""
from __future__ import annotations

import fnmatch

from .util import dumps, iso, loads, uid

EVENT_TYPES = [
    "task.created", "task.completed", "task.deferred", "task.updated", "task.deleted",
    "project.created", "project.updated", "project.blocked", "project.deleted",
    "goal.created", "goal.updated", "idea.created", "idea.updated",
    "research.created", "research.updated", "knowledge.created",
    "person.created", "person.updated", "interaction.created",
    "relationship.interaction", "relationship.neglected",
    "message.received", "email.received", "commitment.detected",
    "habit.missed", "decision.created", "decision.updated", "calendar.changed",
    "overload.detected", "insight.created", "memory.created", "memory.corrected",
    "workflow.created", "workflow.started", "workflow.completed", "workflow.failed",
    "note.created", "question.created", "learning.created", "review.created",
]

class EventBus:
    def __init__(self, db):
        self.db = db
        self._subscribers: list[tuple[str, callable]] = []

    def subscribe(self, pattern: str, handler):
        """Subscribe a handler to a glob pattern, e.g. 'task.*' or '*'."""
        self._subscribers.append((pattern, handler))

    def emit(self, type_: str, payload: dict, *, actor: str = "system",
             idempotency_key: str | None = None) -> dict | None:
        if idempotency_key and self.db.one(
                "SELECT id FROM events WHERE idempotency_key=?", (idempotency_key,)):
            return None
        event = {"id": uid("evt"), "type": type_, "actor": actor,
                 "payload": payload, "created_at": iso()}
        self.db.execute(
            "INSERT INTO events(id,type,actor,payload,created_at,idempotency_key)"
            " VALUES(?,?,?,?,?,?)",
            (event["id"], type_, actor, dumps(payload), event["created_at"], idempotency_key))
        for pattern, handler in list(self._subscribers):
            if fnmatch.fnmatch(type_, pattern):
                try:
                    handler(event)
                except Exception:
                    pass  # subscribers must never break the writer
        return event

    def list(self, type_: str | None = None, limit: int = 100):
        if type_:
            rows = self.db.query(
                "SELECT * FROM events WHERE type=? ORDER BY created_at DESC LIMIT ?",
                (type_, int(limit)))
        else:
            rows = self.db.query(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (int(limit),))
        return [self._map(r) for r in rows]

    def count_since(self, type_pattern: str, since_iso: str) -> int:
        rows = self.db.query(
            "SELECT type, COUNT(*) n FROM events WHERE created_at>? GROUP BY type",
            (since_iso,))
        return sum(r["n"] for r in rows if fnmatch.fnmatch(r["type"], type_pattern))

    @staticmethod
    def _map(row) -> dict:
        return {"id": row["id"], "type": row["type"], "actor": row["actor"],
                "payload": loads(row["payload"]), "created_at": row["created_at"]}
