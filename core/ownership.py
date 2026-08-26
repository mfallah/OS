"""Data ownership: export, backup, restore and full deletion with audit."""
from __future__ import annotations

from .util import dumps, iso, loads

class DataOwnership:
    def __init__(self, db, entities, memory, events, permissions):
        self.db = db
        self.entities = entities
        self.memory = memory
        self.events = events
        self.permissions = permissions

    def export_all(self) -> dict:
        """Portable, self-describing export of everything the OS holds."""
        entities = self.entities.list(limit=10_000)
        memories = self.memory.list(limit=10_000, include_disabled=True)
        edges = self.entities.db.query("SELECT * FROM edges")
        events = self.events.list(limit=10_000)
        prefs = {r["key"]: loads(r["value"]) for r in
                 self.db.query("SELECT * FROM preferences")}
        export = {"format": "ourex.export.v1", "exported_at": iso(),
                  "entities": entities, "memories": memories,
                  "edges": [dict(e) for e in edges], "events": events,
                  "preferences": prefs,
                  "counts": {"entities": len(entities), "memories": len(memories),
                             "edges": len(edges), "events": len(events)}}
        self.events.emit("data.exported", {"counts": export["counts"]}, actor="user")
        return export

    def backup(self) -> dict:
        backup = self.export_all()
        backup["kind"] = "backup"
        return backup

    def restore(self, export: dict, *, actor: str = "user") -> dict:
        if not isinstance(export, dict) or not str(export.get("format", "")).startswith("ourex."):
            raise ValueError("not a recognized myos export document")
        restored = 0
        for ent in export.get("entities", []):
            kind = ent.pop("kind", None)
            if not kind:
                continue
            clean = {k: v for k, v in ent.items()
                     if k not in {"created_at", "updated_at"}}
            clean.pop("id", None)
            self.entities.create(kind, clean, actor=actor)
            restored += 1
        mem_restored = 0
        for mem in export.get("memories", []):
            self.memory.remember(mem.get("category", "temporary"), mem.get("content", ""),
                                 confidence=mem.get("confidence", 0.5),
                                 source=f"restore:{mem.get('source', 'unknown')}",
                                 importance=mem.get("importance", 5))
            mem_restored += 1
        self.events.emit("data.restored", {"entities": restored, "memories": mem_restored},
                         actor=actor)
        return {"restored_entities": restored, "restored_memories": mem_restored}

    def delete_everything(self, *, actor: str = "user") -> dict:
        # right to be forgotten: hard-delete content tables, keep the audit of deletion
        for table in ("entities", "edges", "memories", "events", "notifications",
                      "workflow_runs", "approvals"):
            self.db.execute(f"DELETE FROM {table}")
        policy = self.permissions.authorize("data.delete_everything", level="sensitive",
                                            approved=True, actor=actor,
                                            result={"scope": "all user content"})
        return {"deleted": True, "audit": policy}
