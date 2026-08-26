"""Personal graph: typed, directed relations between any two entities.

Example chain: User -> Goal -> Project -> Task -> Decision -> Research ->
Knowledge -> Document -> Person. Edges carry provenance (created_by) so the
graph can distinguish user-asserted structure from system-inferred structure.
"""
from __future__ import annotations

from .util import iso

RELATIONS = {
    "supports", "blocks", "depends_on", "related_to", "derived_from",
    "originated_from", "owned_by", "belongs_to", "connected_to", "resulted_in",
    "mentioned_in", "learned_from", "follows_up", "conflicts_with", "contributes_to",
}

class GraphError(ValueError):
    pass

class Graph:
    def __init__(self, db, entities, events):
        self.db = db
        self.entities = entities
        self.events = events

    def link(self, source: str, relation: str, target: str, *, actor: str = "user") -> dict:
        relation = (relation or "").strip().lower()
        if relation not in RELATIONS:
            raise GraphError(f"unknown relation: {relation or '<empty>'}")
        if not self.entities.get(source):
            raise GraphError(f"source entity not found: {source}")
        if not self.entities.get(target):
            raise GraphError(f"target entity not found: {target}")
        if source == target:
            raise GraphError("self-links are not allowed")
        self.db.execute(
            "INSERT OR IGNORE INTO edges(source,relation,target,created_at,created_by)"
            " VALUES(?,?,?,?,?)", (source, relation, target, iso(), actor))
        self.events.emit("graph.linked", {"source": source, "relation": relation,
                                          "target": target}, actor=actor)
        return {"source": source, "relation": relation, "target": target}

    def unlink(self, source: str, relation: str, target: str, *, actor: str = "user") -> dict:
        cur = self.db.execute(
            "DELETE FROM edges WHERE source=? AND relation=? AND target=?",
            (source, relation, target))
        self.events.emit("graph.unlinked", {"source": source, "relation": relation,
                                            "target": target}, actor=actor)
        return {"removed": cur.rowcount > 0}

    def neighbors(self, entity_id: str, relation: str | None = None,
                  direction: str = "both") -> list[dict]:
        sql, args = self._neighbor_sql(entity_id, relation, direction)
        edges = [dict(r) for r in self.db.query(sql, args)]
        for edge in edges:
            other = edge["target"] if edge["source"] == entity_id else edge["source"]
            entity = self.entities.get(other)
            edge["entity"] = entity
            edge["edge_direction"] = "outgoing" if edge["source"] == entity_id else "incoming"
        return edges

    def edges_for_kind(self, limit: int = 500) -> list[dict]:
        rows = self.db.query("SELECT * FROM edges ORDER BY created_at DESC LIMIT ?",
                             (int(limit),))
        return [dict(r) for r in rows]

    def path(self, start: str, goal: str, max_depth: int = 4) -> list[str] | None:
        """Breadth-first path between two entities (used by 'why is this related?')."""
        if start == goal:
            return [start]
        visited, frontier = {start}, [(start, [start])]
        for _ in range(max_depth):
            next_frontier = []
            for node, trail in frontier:
                sql, args = self._neighbor_sql(node, None, "both")
                for edge in self.db.query(sql, args):
                    nxt = edge["target"] if edge["source"] == node else edge["source"]
                    if nxt in visited:
                        continue
                    if nxt == goal:
                        return trail + [nxt]
                    visited.add(nxt)
                    next_frontier.append((nxt, trail + [nxt]))
            frontier = next_frontier
        return None

    @staticmethod
    def _neighbor_sql(entity_id, relation, direction):
        clauses, args = [], []
        if direction in ("both", "outgoing"):
            clauses.append("source=?"); args.append(entity_id)
        if direction in ("both", "incoming"):
            clauses.append("target=?"); args.append(entity_id)
        sql = "SELECT * FROM edges WHERE (" + " OR ".join(clauses) + ")"
        if relation:
            sql += " AND relation=?"; args.append(relation)
        return sql, args
