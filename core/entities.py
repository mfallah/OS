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

#: Status vocabularies per kind — used by the schema endpoint so the UI can
#: offer rich, kind-aware forms without hardcoding vocabularies twice.
KIND_STATUSES = {
    "task": ["open", "in-progress", "waiting", "done", "archived", "cancelled"],
    "project": ["active", "at-risk", "paused", "done", "archived"],
    "idea": ["captured", "developing", "validated", "parked", "done"],
    "goal": ["active", "achieved", "parked", "archived"],
    "person": ["active", "dormant", "archived"],
    "decision": ["open", "decided", "reviewed", "archived"],
    "question": ["open", "answered", "archived"],
    "research": ["active", "paused", "concluded", "archived"],
    "knowledge": ["draft", "distilled", "archived"],
    "note": ["inbox", "processed", "archived"],
    "habit": ["building", "steady", "broken", "archived"],
    "routine": ["draft", "active", "paused", "archived"],
    "commitment": ["made", "kept", "broken"],
}

#: Suggested fields per kind. These are *suggestions only* — the store accepts
#: any extra field on any entity (schema-flexible by design), and the UI reads
#: this catalog to offer creative data entry without artificial limits.
KIND_FIELD_SUGGESTIONS = {
    "task": [
        {"name": "title", "label": "Title", "type": "text", "required": True},
        {"name": "project", "label": "Project", "type": "text"},
        {"name": "priority", "label": "Priority", "type": "enum",
         "options": ["low", "medium", "high", "urgent"]},
        {"name": "due", "label": "Due", "type": "date"},
        {"name": "start", "label": "Start", "type": "date"},
        {"name": "estimate", "label": "Estimate (min)", "type": "number"},
        {"name": "energy", "label": "Energy", "type": "enum", "options": ["light", "deep"]},
        {"name": "recurrence", "label": "Repeat", "type": "text",
         "placeholder": "daily / weekly on Mon / every 3 days"},
        {"name": "depends_on", "label": "Blocked by (entity id)", "type": "text"},
        {"name": "notes", "label": "Notes", "type": "textarea"},
    ],
    "project": [
        {"name": "name", "label": "Name", "type": "text", "required": True},
        {"name": "description", "label": "Description", "type": "textarea"},
        {"name": "vision", "label": "Vision — what does done look like?", "type": "textarea"},
        {"name": "next_action", "label": "Next concrete action", "type": "text"},
        {"name": "progress", "label": "Progress %", "type": "number"},
        {"name": "deadline", "label": "Target date", "type": "date"},
        {"name": "area", "label": "Life area", "type": "text"},
    ],
    "person": [
        {"name": "name", "label": "Name", "type": "text", "required": True},
        {"name": "role", "label": "Role / relationship", "type": "text"},
        {"name": "importance", "label": "Importance", "type": "enum",
         "options": ["low", "medium", "high"]},
        {"name": "need", "label": "Current need / context", "type": "textarea"},
        {"name": "communication_preference", "label": "Communication preference", "type": "text"},
        {"name": "last_contact", "label": "Last contact", "type": "date"},
        {"name": "birthday", "label": "Birthday", "type": "date"},
        {"name": "topics", "label": "Shared topics", "type": "list"},
    ],
    "idea": [
        {"name": "title", "label": "Idea", "type": "text", "required": True},
        {"name": "summary", "label": "Summary", "type": "textarea"},
        {"name": "potential", "label": "Potential", "type": "enum",
         "options": ["unknown", "low", "medium", "high"]},
        {"name": "first_step", "label": "Smallest next experiment", "type": "text"},
    ],
    "note": [
        {"name": "title", "label": "Title", "type": "text", "required": True},
        {"name": "body", "label": "Body", "type": "textarea"},
        {"name": "source", "label": "Source", "type": "text"},
    ],
    "decision": [
        {"name": "title", "label": "Question", "type": "text", "required": True},
        {"name": "context", "label": "Context", "type": "textarea"},
        {"name": "options", "label": "Options", "type": "list"},
        {"name": "decision", "label": "Chosen option", "type": "text"},
        {"name": "confidence", "label": "Confidence 0–1", "type": "number"},
        {"name": "reversible", "label": "Reversible?", "type": "enum", "options": ["yes", "no"]},
    ],
}

#: Universal fallback — offered on every kind so no entity type is a dead end.
UNIVERSAL_FIELDS = [
    {"name": "title", "label": "Title", "type": "text", "required": True},
    {"name": "description", "label": "Description", "type": "textarea"},
    {"name": "status", "label": "Status", "type": "text"},
]

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

    def list(self, kind: str | None = None, limit: int = 200, status: str | None = None,
             tag: str | None = None, q: str | None = None):
        """List entities with optional kind/status filters (SQL) and tag/text
        filters (post-hydration — personal scale makes this the honest trade)."""
        sql = "SELECT * FROM entities WHERE deleted_at IS NULL"
        args: list = []
        if kind:
            sql += " AND kind=?"; args.append(kind)
        if status:
            sql += " AND status=?"; args.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"; args.append(max(int(limit) * 4, 200))
        items = [self._hydrate(r) for r in self.db.query(sql, args)]
        if tag:
            items = [e for e in items if tag in (e.get("tags") or [])]
        if q:
            needle = q.lower()
            items = [e for e in items if needle in title_of(e).lower()
                     or needle in str(e.get("description") or "").lower()
                     or needle in str(e.get("name") or "").lower()]
        return items[: int(limit)]

    def history(self, entity_id: str, limit: int = 50) -> list[dict]:
        """Event trail for one entity — provenance for every change."""
        rows = self.db.query(
            "SELECT type, actor, payload, created_at FROM events "
            "ORDER BY created_at DESC LIMIT 2000")
        out = []
        for r in rows:
            payload = loads(r["payload"])
            if payload.get("entity_id") == entity_id:
                out.append({"type": r["type"], "actor": r["actor"],
                            "payload": payload, "created_at": r["created_at"]})
                if len(out) >= int(limit):
                    break
        return out

    # ------------------------------------------------------------ bulk writes
    def bulk_update(self, ids: list[str], patch: dict, *, actor: str = "user") -> dict:
        updated, missing = [], []
        for entity_id in ids:
            try:
                updated.append(self.update(entity_id, dict(patch), actor=actor)["id"])
            except KeyError:
                missing.append(entity_id)
        return {"updated": updated, "missing": missing}

    def bulk_tag(self, ids: list[str], tag: str, *, remove: bool = False,
                 actor: str = "user") -> dict:
        touched, missing = [], []
        for entity_id in ids:
            try:
                row = self._row(entity_id)
            except KeyError:
                missing.append(entity_id)
                continue
            data = loads(row["data"])
            tags = [t for t in (data.get("tags") or []) if t]
            if remove:
                tags = [t for t in tags if t != tag]
            elif tag not in tags:
                tags.append(tag)
            touched.append(entity_id)
            self.update(entity_id, {"tags": tags}, actor=actor)
        return {"tagged": touched, "missing": missing, "tag": tag, "removed": remove}

    def bulk_delete(self, ids: list[str], *, actor: str = "user") -> dict:
        deleted, missing = [], []
        for entity_id in ids:
            try:
                deleted.append(self.delete(entity_id, actor=actor)["id"])
            except KeyError:
                missing.append(entity_id)
        return {"deleted": deleted, "missing": missing}

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
