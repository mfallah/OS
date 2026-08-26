"""Daily / weekly / monthly planning.

The daily plan is capacity-aware: it never fills the whole day, respects energy
and constitution non-negotiables, and always leaves slack. Weekly and monthly
reviews aggregate real events and entity state into an explainable narrative.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

class Planner:
    def __init__(self, entities, events, state, insights):
        self.entities = entities
        self.events = events
        self.state = state
        self.insights = insights

    def daily_plan(self, *, available_hours: float | None = None) -> dict:
        snap = self.state.compute()
        capacity = available_hours if available_hours is not None else \
            snap["attention_budget"]["deep_work_hours_available"] + 2.0
        target_fill = round(capacity * 0.7, 1)  # never plan 100% of the day
        energy = snap["energy"]["level"]

        tasks = [t for t in self.entities.list("task", limit=300)
                 if t.get("status") not in {"done", "completed", "archived", "cancelled"}]
        scored = sorted(tasks, key=self._priority_score, reverse=True)
        plan, minutes = [], 0
        skipped = []
        for task in scored:
            est = float(task.get("estimate") or 25)
            if task.get("energy") == "deep" and energy == "low":
                skipped.append({"task": task.get("title"), "reason": "deep work skipped: low energy"})
                continue
            if (minutes + est) / 60 > target_fill:
                skipped.append({"task": task.get("title"), "reason": "capacity reached; protected slack"})
                continue
            plan.append({"task_id": task["id"], "title": task.get("title"),
                         "estimate": est, "energy": task.get("energy", "light"),
                         "why": self._why(task, snap)})
            minutes += int(est)
        return {"date": snap["date"], "capacity_hours": capacity,
                "planned_minutes": minutes, "slack_hours": round(capacity - minutes / 60, 1),
                "energy": energy, "items": plan, "deliberately_skipped": skipped,
                "rule": "fill at most 70% of available capacity; deep work only when energy allows"}

    def _priority_score(self, task) -> float:
        score = {"high": 30, "medium": 15, "low": 5}.get(str(task.get("priority", "medium")), 15)
        due = str(task.get("due") or "")
        score += {"Today": 25, "Tomorrow": 12, "Yesterday": 40, "Overdue": 40}.get(due, 0)
        score += float(task.get("priority_weight") or 0)
        if task.get("project"):
            score += 5
        return score

    @staticmethod
    def _why(task, snap) -> str:
        reasons = []
        if str(task.get("due")) in {"Today", "Yesterday", "Overdue"}:
            reasons.append(f"due: {task.get('due')}")
        if task.get("priority") == "high":
            reasons.append("high priority")
        if task.get("project"):
            reasons.append(f"supports {task['project']}")
        return "; ".join(reasons) or "best available next action"

    # ---------------------------------------------------------------- reviews
    def weekly_review(self) -> dict:
        week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        events = self.events.list(limit=500)
        recent = [e for e in events if e["created_at"] >= week_ago]
        wins = [e for e in recent if e["type"] == "task.completed"
                or e["type"].endswith(".completed")]
        created = [e for e in recent if e["type"].endswith(".created")]
        snap = self.state.compute()
        insights = self.insights.generate()
        risks = [i for i in insights if i["kind"] == "Risk"]
        opportunities = [i for i in insights if i["kind"] == "Opportunity"]
        return {"period": "last 7 days", "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "wins": [{"title": e["payload"].get("title") or e["type"]} for e in wins][:10],
                "counts": {"completed": len(wins), "created": len(created),
                           "total_events": len(recent)},
                "unfinished": snap["workload"],
                "risks": risks, "opportunities": opportunities,
                "relationships": [p.get("name") for p in snap["relationship_needs"]],
                "projects": [{"name": p.get("name") or p.get("title"),
                              "health": p.get("health", {}).get("status")}
                             for p in snap["projects"][:6]],
                "life_debt": snap["life_debt"],
                "next_week_strategy": self._strategy(snap, risks)}

    def monthly_review(self) -> dict:
        snap = self.state.compute()
        month_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        events = [e for e in self.events.list(limit=1000) if e["created_at"] >= month_ago]
        return {"period": "last 30 days", "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "state_of_life": {
                    "work": {"open_tasks": snap["workload"]["open_tasks"],
                             "completed_30d": len([e for e in events if e["type"] == "task.completed"])},
                    "projects": [{"name": p.get("name") or p.get("title"),
                                  "status": p.get("status"),
                                  "health": p.get("health", {}).get("score")}
                                 for p in snap["projects"]],
                    "learning": len(self.entities.list("learning", limit=100)),
                    "relationships": {"total": len(self.entities.list("person", limit=200)),
                                      "needing_attention": len(snap["relationship_needs"])},
                    "habits": len(self.entities.list("habit", limit=100)),
                    "ideas": len(self.entities.list("idea", limit=200)),
                    "research": len(self.entities.list("research", limit=100)),
                    "decisions": {"open": len(snap["unresolved_decisions"]),
                                  "made_30d": len([e for e in events if e["type"] == "decision.created"])},
                    "cognitive_load": snap["cognitive_load"],
                    "life_debt": snap["life_debt"],
                    "activity_events": len(events)},
                "strategy": self._strategy(snap, [i for i in self.insights.generate()
                                                  if i["kind"] == "Risk"])}

    @staticmethod
    def _strategy(snap, risks) -> list[str]:
        moves = []
        if snap["life_debt"]["total"] > 0:
            biggest = max(snap["life_debt"]["items"], key=lambda i: i["count"])
            moves.append(f"Pay down the biggest debt first: {biggest['detail']}.")
        if snap["cognitive_load"]["score"] >= 60:
            moves.append("Reduce active load before committing to new work.")
        if risks:
            moves.append(f"Resolve the highest-confidence risk: {risks[0]['title']}.")
        if not moves:
            moves.append("Steady state: protect deep-work windows and keep shipping.")
        return moves
