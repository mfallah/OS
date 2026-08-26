"""Insight, pattern and friction engine.

Insights are observations with reasoning and confidence — never diagnoses.
Each insight links to the entities it was derived from, states the rule that
produced it, and proposes a concrete next action. Frictions come with a
matching intervention.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

class InsightEngine:
    def __init__(self, entities, events, state: "PersonalState"):
        self.entities = entities
        self.events = events
        self.state = state

    # ------------------------------------------------------------- insights
    def generate(self) -> list[dict]:
        snap = self.state.compute()
        insights: list[dict] = []
        insights += self._load_insights(snap)
        insights += self._project_insights(snap)
        insights += self._relationship_insights(snap)
        insights += self._decision_insights(snap)
        insights += self._pattern_insights()
        for i, ins in enumerate(insights):
            ins["id"] = f"ins_{i:03d}"
        return insights

    def _load_insights(self, snap) -> list[dict]:
        load = snap["cognitive_load"]
        out = []
        if load["score"] >= 75:
            top = sorted(load["factors"], key=lambda f: f["contribution"], reverse=True)[:2]
            out.append({"kind": "Risk", "title": "Cognitive overload territory",
                        "body": f"Load is {load['score']}/100, driven by "
                                + " and ".join(f"{f['count']} {f['factor']}" for f in top)
                                + ". Defer or delegate before adding anything new.",
                        "confidence": 0.9, "reasoning": load["explanation"],
                        "entities": [], "action": "Open the daily plan and cut two items."})
        elif snap["workload"]["overdue"]:
            out.append({"kind": "Risk", "title": "Overdue work is compounding",
                        "body": f"{snap['workload']['overdue']} items are past due. "
                                "Overdue work weighs 8× more than open loops in your load score.",
                        "confidence": 0.86, "reasoning": "overdue factor in cognitive load model",
                        "entities": [], "action": "Reschedule or close overdue items today."})
        return out

    def _project_insights(self, snap) -> list[dict]:
        out = []
        for p in snap["projects"]:
            health = self.project_health(p)
            p["health"] = health
            if health["status"] == "at-risk":
                out.append({"kind": "Risk", "title": f"“{p.get('name') or p.get('title')}” needs a decision",
                            "body": f"Health is {health['score']}/100: {health['explanation']}",
                            "confidence": 0.8, "reasoning": health["explanation"],
                            "entities": [p["id"]],
                            "action": health.get("suggestion") or "Define the next concrete action."})
            elif health["momentum"] >= 70 and health["score"] >= 70:
                out.append({"kind": "Opportunity",
                            "title": f"“{p.get('name') or p.get('title')}” has momentum",
                            "body": f"Momentum {health['momentum']}/100. Protecting one more "
                                    "deep-work session this week compounds it.",
                            "confidence": 0.72, "reasoning": "recent activity + progress trend",
                            "entities": [p["id"]],
                            "action": "Block a focus window in the calendar."})
        return out

    def _relationship_insights(self, snap) -> list[dict]:
        return [{"kind": "Attention",
                 "title": f"{p.get('name')} may need a meaningful touchpoint",
                 "body": f"Importance is {p.get('importance', 'medium')} and last contact "
                         f"was {p.get('last_contact') or p.get('lastContact') or 'a while ago'}. "
                         "This is an observation, not a score.",
                 "confidence": 0.7,
                 "reasoning": "cadence rule: importance-based contact interval",
                 "entities": [p["id"]], "action": "Draft a follow-up note."}
                for p in snap["relationship_needs"][:3]]

    def _decision_insights(self, snap) -> list[dict]:
        decisions = snap["unresolved_decisions"][:2]
        return [{"kind": "Decision required",
                 "title": f"Open decision: {d.get('title') or d.get('question', 'untitled')}",
                 "body": d.get("context") or "An explicit decision unlocks dependent work.",
                 "confidence": 0.75, "reasoning": "decision entity has status 'open'",
                 "entities": [d["id"]], "action": "Compare options in the decision record."}
                for d in decisions]

    def _pattern_insights(self) -> list[dict]:
        week = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        out = []
        deferrals = self.events.count_since("task.deferred", week)
        if deferrals >= 3:
            out.append({"kind": "Pattern", "title": "Repeated postponement observed",
                        "body": f"{deferrals} tasks were deferred in 7 days. Observation: the "
                                "scope or timing of planned work may not match available capacity.",
                        "confidence": 0.66, "reasoning": "task.deferred event count over 7 days",
                        "entities": [], "action": "Shrink the next plan to fit real capacity."})
        return out

    # -------------------------------------------------------- project health
    def project_health(self, project: dict) -> dict:
        tasks = [t for t in self.entities.list("task", limit=500)
                 if t.get("project") in (project.get("name"), project.get("title"), project["id"])]
        done = len([t for t in tasks if t.get("status") in {"done", "completed"}])
        open_ = len(tasks) - done
        progress = project.get("progress")
        if progress is None:
            progress = int(done * 100 / len(tasks)) if tasks else 0
        week_events = self.events.count_since("*.updated",
            (datetime.now(UTC) - timedelta(days=7)).isoformat())
        momentum = max(0, min(100, 30 + week_events * 5 - open_ * 4 + done * 8))
        clarity = project.get("clarity") or (70 if project.get("next") or
                                             project.get("next_action") else 40)
        risk = max(0, min(100, 100 - int((int(progress) + momentum + int(clarity)) / 3)
                          + (20 if project.get("status") == "at-risk" else 0)))
        score = max(0, min(100, int((int(progress) * 0.35) + (momentum * 0.3)
                                    + (int(clarity) * 0.25) + ((100 - risk) * 0.1))))
        status = "healthy" if score >= 65 else "watch" if score >= 40 else "at-risk"
        reasons = []
        reasons.append(f"progress {progress}% (weight 35%)")
        reasons.append(f"momentum {momentum}/100 from {week_events} updates this week (30%)")
        reasons.append(f"clarity {clarity}/100 "
                       f"({'next action defined' if clarity >= 60 else 'no clear next action'}) (25%)")
        reasons.append(f"risk {risk}/100 (10%)")
        suggestion = None
        if open_ and not (project.get("next") or project.get("next_action")):
            suggestion = f"Pick one of the {open_} open tasks as the explicit next action."
        return {"score": score, "status": status, "progress": int(progress),
                "momentum": momentum, "clarity": int(clarity), "risk": risk,
                "open_tasks": open_, "done_tasks": done,
                "explanation": "; ".join(reasons), "suggestion": suggestion}

    # --------------------------------------------------------------- friction
    def frictions_for(self, entity: dict) -> list[dict]:
        frictions = []
        if not entity.get("description") and not entity.get("summary"):
            frictions.append({"friction": "ambiguity",
                              "intervention": "write a one-sentence definition of done"})
        if (entity.get("estimate") or 0) >= 120:
            frictions.append({"friction": "excessive scope",
                              "intervention": "split into a 25-minute starter step"})
        if entity.get("energy") == "deep" and self.state.compute()["energy"]["level"] == "low":
            frictions.append({"friction": "low energy",
                              "intervention": "schedule after recovery or swap for a light task"})
        if not entity.get("project"):
            frictions.append({"friction": "missing context",
                              "intervention": "link it to a project, goal or person"})
        return frictions
