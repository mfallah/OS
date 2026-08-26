"""Universal capture + idea clustering + email/calendar intelligence helpers.

Quick Capture turns free text into a typed entity with links and a memory
trace. Type classification is heuristic and always explainable — and every
uncertain guess is marked so the user can correct it.
"""
from __future__ import annotations

from .util import words

CAPTURE_HINTS = [
    (("idea", "what if", "could we", "ایده", "maybe someday"), "idea",
     "contains ideation language"),
    (("decide", "decision", "should i", "should we", "تصمیم"), "decision",
     "decision framing detected"),
    (("learn", "study", "course", "یادگیری", "یاد بگیرم"), "learning",
     "learning intent detected"),
    (("ask", "question", "why ", "how does", "؟"), "question", "framed as a question"),
    (("met ", "call with", "lunch with", "talked to"), "interaction",
     "describes an interaction"),
    (("deadline", "by friday", "paid", "price", "cost", "$"), "project",
     "contains concrete project detail"),
]

EMAIL_SIGNALS = {
    "commitment": ("i will", "i promise", "i'll send", "we will deliver", "commit"),
    "deadline": ("by friday", "by monday", "deadline", "due date", "eod", "end of week"),
    "follow_up": ("following up", "just checking", "gentle reminder", "circling back"),
    "opportunity": ("opportunity", "interested in", "would you be open", "partnership"),
    "decision": ("please confirm", "let me know your decision", "approve", "sign off"),
}

class CaptureService:
    def __init__(self, entities, graph, memory, events, people_suggester=None):
        self.entities = entities
        self.graph = graph
        self.memory = memory
        self.events = events

    # -------------------------------------------------------------- classify
    def classify(self, text: str) -> dict:
        lowered = (text or "").lower()
        for hints, kind, reason in CAPTURE_HINTS:
            if any(h in lowered for h in hints):
                return {"kind": kind, "confidence": 0.72, "reason": reason}
        verbs = ("call", "email", "send", "buy", "book", "finish", "review", "write",
                 "fix", "pay", "запис", "بفرست", "تماس", "بخر")
        if any(v in lowered for v in verbs) or lowered.strip().endswith("!"):
            return {"kind": "task", "confidence": 0.6,
                    "reason": "action verb detected; defaulted to task"}
        return {"kind": "note", "confidence": 0.4,
                "reason": "no strong signal; captured as a note you can re-file"}

    # --------------------------------------------------------------- capture
    def capture(self, text: str, *, entity: str | None = None, actor: str = "user",
                extra: dict | None = None, idempotency_key: str | None = None) -> dict:
        guess = self.classify(text)
        kind = entity or guess["kind"]
        data = dict(extra or {})
        data.setdefault("title", text[:140])
        if kind == "idea":
            data.setdefault("raw_capture", text)
            data.setdefault("status", "captured")
            data.setdefault("potential", "unknown")
        item = self.entities.create(kind, data, actor=actor,
                                    idempotency_key=idempotency_key)
        links = self._auto_link(item, text)
        self.memory.remember(
            "episodic", f"captured {kind}: {text[:100]}",
            confidence=guess["confidence"], source="quick-capture", importance=3,
            why="keeps capture history for continuity; safe to delete")
        return {"entity": item, "classification": guess, "links_created": links,
                "next_step": self._next_step(item)}

    def _auto_link(self, item: dict, text: str) -> list[dict]:
        links = []
        terms = set(words(text))
        text_lower = (text or "").lower()
        for candidate in self.entities.list(limit=200):
            if candidate["id"] == item["id"]:
                continue
            name = str(candidate.get("title") or candidate.get("name") or "").lower()
            # match when the candidate's name words appear in the captured text
            # (or the name is a substring of it) — never a tautological match
            name_tokens = set(words(name))
            matched = name_tokens and (name_tokens & terms or (len(name) > 3 and name in text_lower))
            if name and matched:
                relation = "related_to"
                if candidate["kind"] == "project" and item["kind"] in {"task", "idea", "research"}:
                    relation = "supports" if item["kind"] == "task" else "contributes_to"
                if candidate["kind"] == "person" and item["kind"] == "interaction":
                    relation = "mentioned_in"
                try:
                    self.graph.link(candidate["id"], relation, item["id"], actor="system")
                    links.append({"to": candidate["id"], "title": candidate.get("title")
                                  or candidate.get("name"), "relation": relation})
                except (KeyError, ValueError):
                    continue
        return links[:5]

    @staticmethod
    def _next_step(item: dict) -> str:
        kind = item.get("kind")
        return {"task": "schedule it in your daily plan",
                "idea": "give it one development step or park it",
                "decision": "list the options and pick a review date",
                "question": "attach it to a research thread",
                "interaction": "log any promised follow-up",
                "learning": "link a resource and a first session"}.get(kind, "filed")

    # ------------------------------------------------------------ email intel
    def analyze_message(self, body: str, *, subject: str = "") -> dict:
        lowered = f"{subject}\n{body}".lower()
        findings = []
        for signal, markers in EMAIL_SIGNALS.items():
            hits = [m for m in markers if m in lowered]
            if hits:
                findings.append({"type": signal, "markers": hits,
                                 "confidence": min(0.9, 0.5 + 0.15 * len(hits))})
        noise = not findings
        return {"signals": findings, "is_noise": noise,
                "routing": "digest" if noise else "attention",
                "guardrail": "extractions are suggestions until the user confirms them"}

    # ---------------------------------------------------------- calendar intel
    def analyze_calendar(self, events: list[dict]) -> dict:
        from .state import PersonalState
        _ = PersonalState  # density helper shared with state engine
        density_notes = []
        days: dict[str, list] = {}
        for e in events:
            days.setdefault(str(e.get("date") or "")[:10], []).append(e)
        for day, items in days.items():
            meeting_minutes = sum(float(i.get("duration_minutes") or 60) for i in items)
            if meeting_minutes > 6 * 60:
                density_notes.append({"date": day, "issue": "overcommitment",
                                      "detail": f"{meeting_minutes/60:.1f}h scheduled",
                                      "intervention": "move or shorten one block"})
            if len(items) >= 5:
                density_notes.append({"date": day, "issue": "fragmented time",
                                      "detail": f"{len(items)} separate blocks",
                                      "intervention": "cluster shallow work into one window"})
        conflicts = []
        for day, items in days.items():
            timed = sorted((i for i in items if i.get("start")),
                           key=lambda i: i.get("start"))
            for a, b in zip(timed, timed[1:]):
                if a.get("end") and b.get("start") and a["end"] > b["start"]:
                    conflicts.append({"date": day, "between": [a.get("title"), b.get("title")],
                                      "intervention": "resolve the overlap before it decides for you"})
        deep_work = [{"date": d, "window": "protected 90-minute block",
                      "intervention": "book it before the calendar fills"}
                     for d, items in days.items() if len(items) <= 2]
        return {"conflicts": conflicts, "density_issues": density_notes,
                "deep_work_opportunities": deep_work[:3]}
