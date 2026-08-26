"""Governed memory: layered, sourced, correctable, exportable, forgettable.

Every memory carries provenance (who created it and why), confidence, scope and
optional expiry. Uncertain machine assumptions are never silently promoted to
identity facts: anything below the confirmation threshold stays 'unconfirmed'
until the user confirms or corrects it. Users can inspect, edit, correct,
delete, export, clear and disable entire categories, and see *why* a memory
exists at all.
"""
from __future__ import annotations

from .util import dumps, iso, loads, uid

CATEGORIES = {
    "identity", "preference", "goal", "project", "relationship", "knowledge",
    "research", "decision", "pattern", "episodic", "temporary",
}

#: Below this confidence a memory is an unconfirmed assumption, never a fact.
CONFIRMATION_THRESHOLD = 0.6

class MemoryStore:
    def __init__(self, db, events):
        self.db = db
        self.events = events

    def remember(self, category: str, content: str, *, confidence: float = 0.5,
                 source: str = "user", provenance: str | None = None,
                 scope: str = "personal", importance: int = 5,
                 expires_at: str | None = None, why: str | None = None,
                 created_by: str = "system") -> dict:
        if category not in CATEGORIES:
            raise ValueError(f"unknown memory category: {category}")
        status = "active" if confidence >= CONFIRMATION_THRESHOLD or source == "user" \
            else "unconfirmed"
        mid = uid("mem")
        now = iso()
        self.db.execute(
            "INSERT INTO memories(id,category,content,confidence,source,provenance,scope,"
            "importance,status,corrected_by_user,created_by,why,expires_at,created_at,"
            "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, category, content, float(confidence), source, provenance or source,
             scope, int(importance), status, 0, created_by,
             why or f"Remembered from {source}", expires_at, now, now))
        self.events.emit("memory.created", {"memory_id": mid, "category": category},
                         actor=created_by)
        return self.get(mid)

    def get(self, memory_id: str) -> dict | None:
        row = self.db.one("SELECT * FROM memories WHERE id=?", (memory_id,))
        return self._map(row) if row else None

    def list(self, category: str | None = None, query: str | None = None,
             limit: int = 50, include_disabled: bool = False) -> list[dict]:
        disabled = set(self.disabled_categories()) if not include_disabled else set()
        sql = ("SELECT * FROM memories WHERE status!='deleted' "
               "AND (expires_at IS NULL OR expires_at>?)")
        args: list = [iso()]
        if category:
            sql += " AND category=?"; args.append(category)
        if query:
            sql += " AND content LIKE ?"; args.append(f"%{query}%")
        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"; args.append(int(limit))
        return [self._map(r) for r in self.db.query(sql, args)
                if r["category"] not in disabled]

    def relevant(self, terms: list[str], limit: int = 8) -> list[dict]:
        """Score memories by term overlap * importance * recency, with reasons."""
        candidates = self.list(limit=300)
        scored = []
        for mem in candidates:
            hay = mem["content"].lower()
            hits = [t for t in terms if t in hay]
            score = len(hits) * 2 + mem["importance"] * 0.3 + mem["confidence"]
            if hits:
                scored.append((score, mem, f"matched: {', '.join(hits[:4])}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{**m, "retrieval_reason": reason} for _, m, reason in scored[:limit]]

    def correct(self, memory_id: str, content: str, *, actor: str = "user") -> dict:
        mem = self._require(memory_id)
        self.db.execute(
            "UPDATE memories SET content=?, confidence=1.0, status='active',"
            " corrected_by_user=1, updated_at=? WHERE id=?",
            (content, iso(), memory_id))
        self.events.emit("memory.corrected", {"memory_id": memory_id,
                                              "category": mem["category"]}, actor=actor)
        return self.get(memory_id)

    def confirm(self, memory_id: str, *, actor: str = "user") -> dict:
        self._require(memory_id)
        self.db.execute(
            "UPDATE memories SET status='active', confidence=MAX(confidence, 0.9),"
            " updated_at=? WHERE id=?", (iso(), memory_id))
        return self.get(memory_id)

    def delete(self, memory_id: str, *, actor: str = "user") -> dict:
        self._require(memory_id)
        self.db.execute("UPDATE memories SET status='deleted', updated_at=? WHERE id=?",
                        (iso(), memory_id))
        self.events.emit("memory.deleted", {"memory_id": memory_id}, actor=actor)
        return {"id": memory_id, "status": "deleted"}

    def export(self) -> dict:
        return {"exported_at": iso(), "memories": self.list(limit=5000, include_disabled=True)}

    def clear(self, *, actor: str = "user") -> dict:
        self.db.execute("UPDATE memories SET status='deleted', updated_at=?", (iso(),))
        self.events.emit("memory.cleared", {}, actor=actor)
        return {"cleared": True}

    def disable_category(self, category: str) -> dict:
        self._set_category_pref(category, False)
        return {"category": category, "enabled": False}

    def enable_category(self, category: str) -> dict:
        self._set_category_pref(category, True)
        return {"category": category, "enabled": True}

    def disabled_categories(self) -> list[str]:
        rows = self.db.query("SELECT key FROM preferences WHERE key LIKE 'memory.off.%'")
        return [r["key"][len("memory.off."):] for r in rows]

    def stats(self) -> dict:
        rows = self.db.query(
            "SELECT category, COUNT(*) n FROM memories WHERE status='active' GROUP BY category")
        unconfirmed = self.db.one(
            "SELECT COUNT(*) n FROM memories WHERE status='unconfirmed'")["n"]
        return {"by_category": {r["category"]: r["n"] for r in rows},
                "unconfirmed": unconfirmed,
                "disabled_categories": self.disabled_categories()}

    def _set_category_pref(self, category: str, enabled: bool):
        if category not in CATEGORIES:
            raise ValueError(f"unknown memory category: {category}")
        key = f"memory.off.{category}"
        if enabled:
            self.db.execute("DELETE FROM preferences WHERE key=?", (key,))
        else:
            self.db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)",
                            (key, iso()))

    def _require(self, memory_id: str):
        mem = self.get(memory_id)
        if not mem or mem["status"] == "deleted":
            raise KeyError(memory_id)
        return mem

    @staticmethod
    def _map(row) -> dict:
        return {"id": row["id"], "category": row["category"], "content": row["content"],
                "confidence": row["confidence"], "source": row["source"],
                "provenance": row["provenance"], "scope": row["scope"],
                "importance": row["importance"], "status": row["status"],
                "corrected_by_user": bool(row["corrected_by_user"]),
                "created_by": row["created_by"], "why": row["why"],
                "expires_at": row["expires_at"], "created_at": row["created_at"],
                "updated_at": row["updated_at"]}
