"""Personal state: a computed, explainable snapshot of the user's reality.

Cognitive load and life debt are computed from explicit, inspectable factors —
never opaque scores. Every number ships with the factor list that produced it,
so the UI can explain *why* the load is what it is.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .util import clamp, today

UTC = timezone.utc
OPEN_STATUSES = {"open", "active", "in-progress", "pending", "blocked", "at-risk"}
DONE_STATUSES = {"done", "completed", "archived", "cancelled"}

LOAD_WEIGHTS = {"open_loop": 3, "active_project": 6, "deadline_soon": 5,
                "overdue": 8, "commitment": 3, "unresolved_decision": 4,
                "relationship_overdue": 3, "unread_notification": 1}

class PersonalState:
    def __init__(self, entities, events, notifications=None):
        self.entities = entities
        self.events = events
        self.notifications = notifications

    # ------------------------------------------------------------- snapshots
    def compute(self) -> dict:
        tasks = self.entities.list("task", limit=500)
        projects = [p for p in self.entities.list("project", limit=200)
                    if p.get("status") != "archived"]
        decisions = self.entities.list("decision", limit=200)
        people = self.entities.list("person", limit=200)
        commitments = self.entities.list("commitment", limit=200)
        calendar = self.entities.list("calendar_event", limit=200)
        habits = self.entities.list("habit", limit=100)

        open_tasks = [t for t in tasks if t.get("status") not in DONE_STATUSES]
        overdue_tasks = [t for t in open_tasks if self._is_overdue(t)]
        due_soon = [t for t in open_tasks if self._due_soon(t) and t not in overdue_tasks]
        open_decisions = [d for d in decisions if d.get("status") in OPEN_STATUSES | {"undecided"}]
        open_commitments = [c for c in commitments if c.get("status") in OPEN_STATUSES]
        rel_needs = [p for p in people if self._relationship_overdue(p)]

        load = self._cognitive_load(open_tasks, overdue_tasks, due_soon, projects,
                                    open_decisions, open_commitments, rel_needs)
        debt = self._life_debt(open_tasks, overdue_tasks, open_decisions,
                               open_commitments, rel_needs, projects, habits)
        week = self.events.count_since("*", (datetime.now(UTC) - timedelta(days=7)).isoformat())

        return {
            "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "date": today(),
            "workload": {"open_tasks": len(open_tasks), "overdue": len(overdue_tasks),
                         "due_soon": len(due_soon)},
            "active_projects": len([p for p in projects if p.get("status") in OPEN_STATUSES]),
            "projects": projects,
            "open_loops": len(open_tasks),
            "commitments": len(open_commitments),
            "deadlines": len(due_soon) + len(overdue_tasks),
            "relationship_needs": rel_needs,
            "unresolved_decisions": open_decisions,
            "calendar_density": self._calendar_density(calendar),
            "recent_activity_7d": week,
            "cognitive_load": load,
            "life_debt": debt,
            "energy": self._energy(load),
            "attention_budget": self._attention(load, calendar),
        }

    def summary(self) -> dict:
        """Compact version injected into AI context packages."""
        full = self.compute()
        return {"date": full["date"], "open_tasks": full["workload"]["open_tasks"],
                "overdue": full["workload"]["overdue"],
                "active_projects": full["active_projects"],
                "unresolved_decisions": len(full["unresolved_decisions"]),
                "cognitive_load": full["cognitive_load"]["score"],
                "load_band": full["cognitive_load"]["band"],
                "life_debt": full["life_debt"]["total"],
                "energy": full["energy"]["level"]}

    # ------------------------------------------------------------- components
    def _cognitive_load(self, open_tasks, overdue, due_soon, projects, decisions,
                        commitments, rel_needs) -> dict:
        factors = []
        def add(label, count, weight, key):
            if count:
                factors.append({"factor": label, "count": count, "weight": weight,
                                "contribution": count * weight})
        active_projects = len([p for p in projects if p.get("status") in OPEN_STATUSES])
        add("open loops", len(open_tasks), LOAD_WEIGHTS["open_loop"], "open_loop")
        add("active projects", active_projects, LOAD_WEIGHTS["active_project"], "active_project")
        add("deadlines within 48h", len(due_soon), LOAD_WEIGHTS["deadline_soon"], "deadline_soon")
        add("overdue work", len(overdue), LOAD_WEIGHTS["overdue"], "overdue")
        add("open commitments", len(commitments), LOAD_WEIGHTS["commitment"], "commitment")
        add("unresolved decisions", len(decisions), LOAD_WEIGHTS["unresolved_decision"], "decision")
        add("relationships needing attention", len(rel_needs),
            LOAD_WEIGHTS["relationship_overdue"], "relationship")
        score = int(clamp(sum(f["contribution"] for f in factors)))
        band = ("calm" if score < 25 else "balanced" if score < 50
                else "loaded" if score < 75 else "overloaded")
        return {"score": score, "band": band, "factors": factors,
                "explanation": "score = " + " + ".join(
                    f"{f['count']}×{f['factor']}" for f in factors) if factors else "minimal open load"}

    def _life_debt(self, open_tasks, overdue, decisions, commitments, rel_needs,
                   projects, habits) -> dict:
        items = [
            {"category": "tasks", "count": len(open_tasks),
             "detail": f"{len(open_tasks)} open tasks ({len(overdue)} overdue)"},
            {"category": "decisions", "count": len(decisions),
             "detail": f"{len(decisions)} decisions waiting on you"},
            {"category": "commitments", "count": len(commitments),
             "detail": f"{len(commitments)} promises still open"},
            {"category": "relationships", "count": len(rel_needs),
             "detail": f"{len(rel_needs)} people need attention"},
            {"category": "projects", "count": len([p for p in projects if p.get("status") == "at-risk"]),
             "detail": "projects at risk"},
            {"category": "habits", "count": len([h for h in habits if h.get("streak", 0) == 0]),
             "detail": "habits without momentum"},
        ]
        items = [i for i in items if i["count"]]
        total = sum(i["count"] for i in items)
        return {"total": total, "items": items,
                "explanation": "sum of unresolved obligations across tasks, decisions, "
                               "commitments, relationships, projects and habits"}

    def _energy(self, load) -> dict:
        score = load["score"]
        level = "high" if score < 30 else "medium" if score < 65 else "low"
        return {"level": level,
                "note": f"inferred from cognitive load {score}/100; adjust manually if off"}

    def _attention(self, load, calendar) -> dict:
        density = self._calendar_density(calendar)
        budget = max(0.0, 8.0 - density["hours_today"]) 
        return {"deep_work_hours_available": round(min(budget, 4.0), 1),
                "fragmentation": density["fragmentation"],
                "note": "reserve protected focus windows before filling the day"}

    @staticmethod
    def _calendar_density(calendar) -> dict:
        todays = [c for c in calendar if str(c.get("date") or c.get("start", ""))[:10] == today()]
        hours = 0.0
        for c in todays:
            dur = c.get("duration_minutes") or 60
            hours += float(dur) / 60
        fragmentation = "low" if len(todays) <= 2 else "moderate" if len(todays) <= 4 else "high"
        return {"events_today": len(todays), "hours_today": round(hours, 1),
                "fragmentation": fragmentation}

    # ------------------------------------------------------------- predicates
    @staticmethod
    def _is_overdue(task) -> bool:
        due = str(task.get("due") or task.get("deadline") or "")
        if due in {"Yesterday", "Overdue"}:
            return True
        try:
            return datetime.fromisoformat(due[:10]).date() < datetime.now(UTC).date()
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _due_soon(task) -> bool:
        due = str(task.get("due") or task.get("deadline") or "")
        if due in {"Today", "Tomorrow"}:
            return True
        try:
            d = datetime.fromisoformat(due[:10]).date()
            return d <= (datetime.now(UTC) + timedelta(days=2)).date()
        except (TypeError, ValueError):
            return False

    def _relationship_overdue(self, person) -> bool:
        importance = str(person.get("importance") or "medium")
        cadence_days = {"high": 7, "medium": 14, "low": 30}.get(importance, 14)
        last = str(person.get("last_contact") or person.get("lastContact") or "")
        if not last:
            return importance == "high"
        rel = {"Today": 0, "Yesterday": 1}
        if last in rel:
            days = rel[last]
        elif last.endswith("days ago"):
            try:
                days = int(last.split()[0])
            except ValueError:
                days = cadence_days + 1
        else:
            try:
                days = (datetime.now(UTC).date() - datetime.fromisoformat(last[:10]).date()).days
            except (TypeError, ValueError):
                days = cadence_days + 1
        return days > cadence_days
