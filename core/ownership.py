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
        prefs = {}
        for row in self.db.query("SELECT * FROM preferences"):
            try:
                prefs[row["key"]] = loads(row["value"])
            except (TypeError, ValueError):
                # Some legacy/simple preferences are stored as plain strings
                # (for example memory category disable timestamps).
                prefs[row["key"]] = row["value"]
        export = {"format": "myos.export.v1", "exported_at": iso(),
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
        if not isinstance(export, dict) or not str(export.get("format", "")).startswith("myos."):
            raise ValueError("not a recognized myos export document")
        entities = export.get("entities", [])
        memories = export.get("memories", [])
        edges = export.get("edges", [])
        preferences = export.get("preferences", {})
        if not isinstance(entities, list) or not isinstance(memories, list) \
                or not isinstance(edges, list) or not isinstance(preferences, dict):
            raise ValueError("export collections have invalid types")

        restored, skipped = 0, 0
        for original in entities:
            if not isinstance(original, dict):
                skipped += 1
                continue
            ent = dict(original)  # never mutate the caller's export document
            kind = ent.pop("kind", None)
            if not kind:
                skipped += 1
                continue
            clean = {k: v for k, v in ent.items()
                     if k not in {"created_at", "updated_at", "graph"}}
            # Preserve IDs so restored graph edges and external references remain valid.
            try:
                self.entities.create(kind, clean, actor=actor,
                                     idempotency_key=f"restore:{clean.get('id')}"
                                     if clean.get("id") else None)
                restored += 1
            except Exception as exc:
                # Duplicate IDs are safe to skip; malformed domain data is not.
                if "UNIQUE constraint failed: entities.id" not in str(exc):
                    raise
                skipped += 1

        mem_restored = 0
        for mem in memories:
            if not isinstance(mem, dict) or not mem.get("content"):
                continue
            self.memory.remember(
                mem.get("category", "temporary"), mem["content"],
                confidence=mem.get("confidence", 0.5),
                source=f"restore:{mem.get('source', 'unknown')}",
                provenance=mem.get("provenance"), scope=mem.get("scope", "personal"),
                importance=mem.get("importance", 5), expires_at=mem.get("expires_at"),
                why=mem.get("why"), created_by=actor)
            mem_restored += 1

        restored_edges = 0
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            try:
                self.entities.db.execute(
                    "INSERT OR IGNORE INTO edges(source,relation,target,created_at,created_by) "
                    "VALUES(?,?,?,?,?)",
                    (edge["source"], edge["relation"], edge["target"],
                     edge.get("created_at") or iso(), edge.get("created_by") or actor))
                restored_edges += 1
            except KeyError:
                continue

        for key, value in preferences.items():
            self.db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)",
                            (str(key), dumps(value)))

        result = {"entities": restored, "memories": mem_restored,
                  "edges": restored_edges, "skipped_entities": skipped,
                  "preferences": len(preferences)}
        self.events.emit("data.restored", result, actor=actor)
        return {"restored_entities": restored, "restored_memories": mem_restored,
                "restored_edges": restored_edges, "restored_preferences": len(preferences),
                "skipped_entities": skipped}

    def delete_everything(self, *, actor: str = "user") -> dict:
        # right to be forgotten: hard-delete content tables, keep the audit of deletion
        for table in ("entities", "edges", "memories", "events", "notifications",
                      "workflow_runs", "approvals"):
            self.db.execute(f"DELETE FROM {table}")
        policy = self.permissions.authorize("data.delete_everything", level="sensitive",
                                            approved=True, actor=actor,
                                            result={"scope": "all user content"})
        return {"deleted": True, "audit": policy}
