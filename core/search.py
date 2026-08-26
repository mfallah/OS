"""Universal search across every entity kind, with natural-language filters.

Understands lightweight NL operators embedded in free text:
  kind:task  status:done  project:myos  high priority  due today
Everything else is treated as semantic terms with explainable ranking.
"""
from __future__ import annotations

import re

from .util import title_of, words

FILTER_RE = re.compile(r"(kind|status|project|due|priority):([\w\u0600-\u06FF-]+)", re.I)

class UniversalSearch:
    def __init__(self, entities, graph, memory):
        self.entities = entities
        self.graph = graph
        self.memory = memory

    def search(self, query: str, *, limit: int = 40) -> dict:
        filters = {m.group(1).lower(): m.group(2).lower()
                   for m in FILTER_RE.finditer(query or "")}
        free_text = FILTER_RE.sub("", query or "")
        free_text = re.sub(r"\b(high|medium|low)\s+priority\b",
                           lambda m: f"priority:{m.group(1)}", free_text.lower())
        terms = words(re.sub(r"priority:\w+", "", free_text))
        if "priority:" in free_text:
            filters["priority"] = free_text.split("priority:")[1].split()[0]

        results = []
        for ent in self.entities.list(limit=1000):
            if not self._passes(ent, filters):
                continue
            score, reasons = self._score(ent, terms)
            if terms and score == 0:
                continue
            results.append({"id": ent["id"], "kind": ent["kind"],
                            "title": title_of(ent), "status": ent.get("status"),
                            "snippet": self._snippet(ent, terms),
                            "score": score, "why": reasons,
                            "updated_at": ent.get("updated_at")})
        results.sort(key=lambda r: r["score"], reverse=True)

        grouped: dict[str, list] = {}
        for r in results[:limit]:
            grouped.setdefault(r["kind"], []).append(r)
        memory_hits = self.memory.relevant(terms, limit=5) if terms else []
        return {"query": query, "filters": filters, "terms": terms,
                "total": len(results), "results": results[:limit],
                "grouped": grouped,
                "memory_matches": memory_hits,
                "explainability": "results ranked by term matches × field weight + status boost"}

    @staticmethod
    def _passes(ent, filters) -> bool:
        for key, value in filters.items():
            actual = str(ent.get(key) or "").lower()
            if key == "project":
                if value not in actual:
                    return False
            elif actual != value:
                return False
        return True

    @staticmethod
    def _score(ent, terms):
        score, reasons = 0, []
        fields = [("title", title_of(ent), 6), ("name", ent.get("name") or "", 6),
                  ("description", ent.get("description") or "", 3),
                  ("summary", ent.get("summary") or "", 3),
                  ("notes", ent.get("notes") or "", 1)]
        for field, text, weight in fields:
            hits = [t for t in terms if t in str(text).lower()]
            if hits:
                score += len(hits) * weight
                reasons.append(f"{hits[:3]} in {field} ×{weight}")
        if score > 0 and ent.get("status") in {"open", "active", "in-progress"}:
            score += 2
            reasons.append("active status boost")
        return score, reasons

    @staticmethod
    def _snippet(ent, terms) -> str:
        text = str(ent.get("description") or ent.get("summary") or title_of(ent))
        if not terms:
            return text[:120]
        lower = text.lower()
        idx = min((lower.find(t) for t in terms if lower.find(t) >= 0), default=0)
        start = max(0, idx - 30)
        return ("..." if start else "") + text[start:start + 120]
