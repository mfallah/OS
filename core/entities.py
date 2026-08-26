"""Entity store: every piece of user data is a typed, connectable entity.

All entities share standard fields (id, type/kind, title, description, status,
priority, confidence, source, owner, timestamps, metadata) and may link to any
other entity through the graph. Writes are idempotent and emit domain events.
"""
from __future__ import annotations

from .util import dumps, iso, loads, title_of, uid

#: Registry of supported entity kinds -> human label. Unknown kinds are rejected
#: at the API boundary so the domain stays explicit and queryable.
ENTITY_KINDS = {
    "user": "User", "constitution": "Personal Constitution", "state": "Personal State",
    "person": "Person", "goal": "Goal", "value": "Value", "area": "Area",
    "project": "Project", "program": "Program", "task": "Task",
    "commitment": "Commitment", "open_loop": "Open Loop", "idea": "Idea",
    "research": "Research", "knowledge": "Knowledge", "document": "Document",
    "note": "Note", "learning": "Learning Objective", "routine": "Routine",
    "habit": "Habit", "decision": "Decision", "interaction": "Interaction",
    "event": "Event", "calendar_event": "Calendar Event", "message": "Message",
    "email": "Email", "investment": "Investment", "thesis": "Thesis",
    "insight": "Insight", "agent": "Agent", "skill": "Skill", "tool": "Tool",
    "workflow": "Workflow", "notification": "Notification", "review": "Review",
    "pattern": "Pattern", "risk": "Risk", "opportunity": "Opportunity",
    "question": "Question", "resource": "Resource", "memory_note": "Memory Note",
}

class ValidationError(ValueError):
    pass

class EntityStore:
    def __init__(self, db, events):
        self.db = db
        self.events = events

    # ------------------------------------------------------------------ reads
    def count(self, kind: str | None = None) -> int:
        if kind:
            return self.db.one(
                "SELECT COUNT(*) n FROM entities WHERE kind=? AND deleted_at IS NULL", (kind,))["n"]
        return self.db.one("SELECT COUNT(*) n FROM entities WHERE deleted_at IS NULL")["n"]

    def get(self, entity_id: str, include_deleted: bool = False):
        row = self.db.one("SELECT * FROM entities WHERE id=?", (entity_id,))
        if not row or (row["deleted_at"] and not include_deleted):
            return None
        return self._hydrate(row)

    def list(self, kind: str | None = None, limit: int = 200, status: str | None = None):
        sql = "SELECT * FROM entities WHERE deleted_at IS NULL"
        args: list = []
        if kind:
            sql += " AND kind=?"; args.append(kind)
        if status:
            sql += " AND status=?"; args.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"; args.append(int(limit))
        return [self._hydrate(r) for r in self.db.query(sql, args)]

    def since(self, iso_timestamp: str, limit: int = 50):
        rows = self.db.query(
            "SELECT * FROM entities WHERE deleted_at IS NULL AND updated_at>? "
            "ORDER BY updated_at DESC LIMIT ?", (iso_timestamp, int(limit)))
        return [self._hydrate(r) for r in rows]

    # ----------------------------------------------------------------- writes
    def create(self, kind: str, data: dict, *, actor: str = "user",
               idempotency_key: str | None = None) -> dict:
        kind = self._validate_kind(kind)
        if idempotency_key:
            existing = self.db.one(
                "SELECT * FROM entities WHERE idempotency_key=?", (idempotency_key,))
            if existing:
                return self._hydrate(existing)
        entity_id = data.pop("id", None) or uid(kind[:4])
        now = iso()
        payload = dict(data)
        payload.setdefault("status", "active")
        payload.setdefault("confidence", 1.0)
        payload.setdefault("source", actor)
        payload.setdefault("metadata", {})
        payload["id"] = entity_id
        payload["created_at"] = now
        payload["updated_at"] = now
        self.db.execute(
            "INSERT INTO entities(id,kind,data,status,created_at,updated_at,idempotency_key)"
            " VALUES(?,?,?,?,?,?,?)",
            (entity_id, kind, dumps(payload), payload["status"], now, now, idempotency_key))
        self.events.emit(f"{kind}.created", {"entity_id": entity_id, "kind": kind,
                                             "title": title_of(payload)}, actor=actor)
        return self.get(entity_id)

    def update(self, entity_id: str, patch: dict, *, actor: str = "user") -> dict:
        row = self._row(entity_id)
        data = loads(row["data"])
        patch.pop("id", None)
        patch.pop("kind", None)
        data.update(patch)
        data["updated_at"] = iso()
        self.db.execute(
            "UPDATE entities SET data=?, status=?, updated_at=? WHERE id=?",
            (dumps(data), data.get("status"), data["updated_at"], entity_id))
        self.events.emit(f"{row['kind']}.updated",
                         {"entity_id": entity_id, "kind": row["kind"], "patch_keys": sorted(patch)},
                         actor=actor)
        return self.get(entity_id)

    def delete(self, entity_id: str, *, actor: str = "user") -> dict:
        """Soft delete: recoverable, auditable, and event-sourced."""
        row = self._row(entity_id)
        now = iso()
        self.db.execute("UPDATE entities SET deleted_at=? WHERE id=?", (now, entity_id))
        self.db.execute("DELETE FROM edges WHERE source=? OR target=?", (entity_id, entity_id))
        self.events.emit(f"{row['kind']}.deleted",
                         {"entity_id": entity_id, "kind": row["kind"]}, actor=actor)
        return {"id": entity_id, "deleted_at": now}

    def restore(self, entity_id: str, *, actor: str = "user") -> dict:
        row = self.db.one("SELECT * FROM entities WHERE id=?", (entity_id,))
        if not row:
            raise KeyError(entity_id)
        self.db.execute("UPDATE entities SET deleted_at=NULL WHERE id=?", (entity_id,))
        self.events.emit(f"{row['kind']}.restored", {"entity_id": entity_id}, actor=actor)
        return self.get(entity_id)

    # ---------------------------------------------------------------- helpers
    def _row(self, entity_id: str):
        row = self.db.one(
            "SELECT * FROM entities WHERE id=? AND deleted_at IS NULL", (entity_id,))
        if not row:
            raise KeyError(entity_id)
        return row

    def _hydrate(self, row) -> dict:
        data = loads(row["data"])
        data["kind"] = row["kind"]
        data["id"] = row["id"]
        return data

    @staticmethod
    def _validate_kind(kind: str) -> str:
        kind = (kind or "").strip().lower()
        if kind not in ENTITY_KINDS:
            raise ValidationError(f"unknown entity kind: {kind or '<empty>'}")
        return kind
