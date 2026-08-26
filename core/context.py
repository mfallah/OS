"""Context engine: bounded, explainable retrieval for every AI request.

Never ships the whole database to a model. Retrieval scores semantic relevance
(term overlap), recency, importance, confidence, relationship to a focal entity
and goal/project alignment, then returns a compact context package where every
item carries its retrieval reason.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .util import clamp, title_of, words

MAX_ENTITIES = 12
MAX_MEMORIES = 8
MAX_NEIGHBORS = 6

class ContextEngine:
    def __init__(self, entities, graph, memory, state_provider, preferences):
        self.entities = entities
        self.graph = graph
        self.memory = memory
        self.state_provider = state_provider
        self.preferences = preferences

    def retrieve(self, query: str = "", *, focal_entity: str | None = None,
                 kinds: list[str] | None = None, limit: int = MAX_ENTITIES) -> dict:
        terms = words(query)
        now = datetime.now(timezone.utc)
        neighbor_ids: set[str] = set()
        neighbors: list[dict] = []
        if focal_entity:
            neighbors = self.graph.neighbors(focal_entity)[:MAX_NEIGHBORS]
            neighbor_ids = {n["target"] if n["source"] == focal_entity else n["source"]
                            for n in neighbors}

        scored = []
        for ent in self.entities.list(limit=400):
            if kinds and ent["kind"] not in kinds:
                continue
            score, reasons = self._score(ent, terms, neighbor_ids, now)
            if score <= 0 and terms:
                continue
            scored.append((score, ent, reasons))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [{**e, "retrieval_reason": "; ".join(r), "relevance": round(s, 2)}
                    for s, e, r in scored[:limit]]

        memories = self.memory.relevant(terms, limit=MAX_MEMORIES) if terms \
            else [{**m, "retrieval_reason": "high importance / recent"}
                  for m in self.memory.list(limit=MAX_MEMORIES)]

        constitution = self._constitution_fragments(terms)
        return {
            "query": query,
            "selected_entities": selected,
            "selected_memories": memories,
            "graph_neighbors": [self._compact(n) for n in neighbors if n.get("entity")],
            "personal_state": self._state_summary(),
            "constitution_fragments": constitution,
            "budget": {"entities": limit, "memories": MAX_MEMORIES,
                       "neighbors": MAX_NEIGHBORS,
                       "note": "context is capped; the full database is never sent"},
            "confidence": self._confidence(selected, memories),
            "retrieval": "semantic terms + recency + importance + confidence + graph proximity",
        }

    def _state_summary(self) -> dict:
        provider = self.state_provider
        try:
            if callable(provider):
                return provider().summary() if hasattr(provider(), "summary") else provider()
            return provider.summary()
        except Exception:
            return {"note": "state unavailable"}

    def _score(self, ent, terms, neighbor_ids, now):
        score, reasons = 0.0, []
        hay = " ".join(str(v) for v in (ent.get("title"), ent.get("name"),
                                        ent.get("description"), ent.get("summary"),
                                        ent.get("status"), ent.get("kind")) if v).lower()
        hits = [t for t in terms if t in hay]
        if hits:
            score += len(hits) * 3
            reasons.append(f"matched terms: {', '.join(hits[:4])}")
        meta = ent.get("metadata") or {}
        pri = meta.get("priority") or ent.get("priority") or 0
        try:
            pri = {"high": 8, "medium": 4, "low": 1}.get(pri, float(pri))
        except (TypeError, ValueError):
            pri = 0
        if pri:
            score += clamp(float(pri), 0, 10) * 0.8
            reasons.append("priority weight")
        try:
            updated = datetime.fromisoformat(ent.get("updated_at", now.isoformat()))
            age_hours = max((now - updated).total_seconds() / 3600, 0)
            recency = max(0.0, 6 - age_hours / 24)
            if recency:
                score += recency
                reasons.append("recently active")
        except (TypeError, ValueError):
            pass
        if ent["id"] in neighbor_ids:
            score += 8
            reasons.append("directly linked to focal entity")
        status = ent.get("status")
        if status in {"active", "in-progress", "at-risk", "open"}:
            score += 2
        return score, reasons

    def _constitution_fragments(self, terms: list[str]) -> list[dict]:
        fragments = []
        for const in self.entities.list("constitution", limit=1):
            for key in ("values", "principles", "non_negotiables", "goals",
                        "priorities", "risk_tolerance", "planning_style",
                        "communication_style", "boundaries"):
                value = const.get(key)
                if not value:
                    continue
                text = value if isinstance(value, list) else [value]
                for item in text:
                    item_text = str(item)
                    if not terms or any(t in item_text.lower() for t in terms):
                        fragments.append({"section": key, "content": item_text,
                                          "reason": "constitution alignment check"})
            if not fragments:
                for key in ("values", "non_negotiables"):
                    for item in const.get(key, [])[:4]:
                        fragments.append({"section": key, "content": str(item),
                                          "reason": "core guidance"})
        return fragments[:8]

    @staticmethod
    def _compact(neighbor: dict) -> dict:
        ent = neighbor.get("entity") or {}
        return {"relation": neighbor["relation"], "direction": neighbor["edge_direction"],
                "id": ent.get("id"), "kind": ent.get("kind"), "title": title_of(ent)}

    @staticmethod
    def _confidence(selected, memories) -> float:
        if not selected and not memories:
            return 0.2
        confs = [m.get("confidence", 0.5) for m in memories]
        base = sum(confs) / len(confs) if confs else 0.5
        return round(min(0.95, base * 0.6 + 0.3), 2)
