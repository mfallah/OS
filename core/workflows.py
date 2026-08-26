"""Workflow engine: Trigger -> Context -> Conditions -> Agent -> Skill -> Tool
-> Action -> Verification -> Notification.

Workflows are first-class entities with risk levels, permissions, approval and
retry policies, timeouts, idempotency keys, notification policies, versioning
and per-run audit records. L2+ actions inside a workflow create approval
requests instead of executing, unless explicitly approved for this run.
"""
from __future__ import annotations

import time

from .util import iso, uid

BUILTIN_WORKFLOWS = [
    {"name": "morning-brief", "trigger": "schedule:07:30",
     "description": "What matters today: plan, capacity, risks, relationships.",
     "risk": "internal",
     "steps": [{"action": "daily_plan"}, {"action": "notify", "category": "Important",
                "title": "Your morning brief is ready"}],
     "approval_policy": "auto", "notification_policy": "deliver-once"},
    {"name": "evening-review", "trigger": "schedule:21:00",
     "description": "Close open loops, capture wins, set tomorrow's first move.",
     "risk": "internal",
     "steps": [{"action": "evening_summary"}, {"action": "notify", "category": "Useful",
                "title": "Evening review ready"}],
     "approval_policy": "auto", "notification_policy": "digest-ok"},
    {"name": "weekly-executive-review", "trigger": "schedule:friday:17:00",
     "description": "Wins, stalls, risks, opportunities and next-week strategy.",
     "risk": "internal",
     "steps": [{"action": "weekly_review"}, {"action": "notify", "category": "Important",
                "title": "Weekly executive review ready"}],
     "approval_policy": "auto", "notification_policy": "deliver-once"},
    {"name": "monthly-state-of-life", "trigger": "schedule:monthly",
     "description": "A whole-life snapshot and next-month strategy.",
     "risk": "internal",
     "steps": [{"action": "monthly_review"}, {"action": "notify", "category": "Important",
                "title": "Monthly state of life ready"}],
     "approval_policy": "auto", "notification_policy": "deliver-once"},
    {"name": "relationship-follow-up", "trigger": "event:relationship.neglected",
     "description": "Notice neglected important relationships and draft a touchpoint.",
     "risk": "external",
     "steps": [{"action": "relationship_scan"},
               {"action": "send_message", "channel": "draft-only"}],
     "approval_policy": "require", "notification_policy": "digest-ok"},
    {"name": "research-continuation", "trigger": "manual",
     "description": "Resume research from prior findings, stale data and open questions.",
     "risk": "internal",
     "steps": [{"action": "research_scan"}, {"action": "notify", "category": "Useful",
                "title": "Research brief updated"}],
     "approval_policy": "auto", "notification_policy": "digest-ok"},
    {"name": "open-loop-cleanup", "trigger": "schedule:daily:18:00",
     "description": "Triage open loops: close, defer or escalate.",
     "risk": "internal",
     "steps": [{"action": "open_loop_scan"}, {"action": "notify", "category": "Useful",
                "title": "Open-loop cleanup suggestions ready"}],
     "approval_policy": "auto", "notification_policy": "digest-ok"},
    {"name": "idea-digest", "trigger": "schedule:weekly",
     "description": "Cluster new ideas, find collisions, propose next steps.",
     "risk": "internal",
     "steps": [{"action": "idea_clusters"}, {"action": "notify", "category": "Interesting",
                "title": "Idea digest ready"}],
     "approval_policy": "auto", "notification_policy": "digest"},
    {"name": "project-risk-monitor", "trigger": "schedule:daily",
     "description": "Watch project health and flag at-risk work early.",
     "risk": "internal",
     "steps": [{"action": "project_health"}, {"action": "notify", "category": "Important",
                "title": "Project risk report"}],
     "approval_policy": "auto", "notification_policy": "threshold"},
    {"name": "learning-review", "trigger": "schedule:weekly",
     "description": "Spaced-recall session across learning objectives.",
     "risk": "internal",
     "steps": [{"action": "learning_scan"}, {"action": "notify", "category": "Interesting",
                "title": "Learning review ready"}],
     "approval_policy": "auto", "notification_policy": "digest"},
    {"name": "inbox-intelligence", "trigger": "event:email.received",
     "description": "Extract tasks, commitments, deadlines and follow-ups from email.",
     "risk": "internal",
     "steps": [{"action": "inbox_scan"}],
     "approval_policy": "auto", "notification_policy": "digest-ok"},
]

class WorkflowEngine:
    def __init__(self, entities, events, permissions, tools, state, planner,
                 insights, notifications, graph, memory):
        self.entities = entities
        self.events = events
        self.permissions = permissions
        self.tools = tools
        self.state = state
        self.planner = planner
        self.insights = insights
        self.notifications = notifications
        self.graph = graph
        self.memory = memory
        self._sync()

    def _sync(self):
        existing = {w.get("name") for w in self.entities.list("workflow", limit=500)}
        for spec in BUILTIN_WORKFLOWS:
            if spec["name"] not in existing:
                self.entities.create("workflow", {**spec, "version": "1.0.0",
                                                  "status": "active", "builtin": True,
                                                  "permissions": ["READ_DATA", "WRITE_DATA"],
                                                  "retry_policy": {"max": 1},
                                                  "timeout_seconds": 30},
                                     actor="system",
                                     idempotency_key=f"workflow:{spec['name']}")

    def list(self) -> list[dict]:
        return self.entities.list("workflow", limit=500)

    def get(self, workflow_id: str) -> dict | None:
        wf = self.entities.get(workflow_id)
        if wf and wf.get("kind") == "workflow":
            return wf
        matches = [w for w in self.list() if w.get("name") == workflow_id]
        return matches[0] if matches else None

    def create(self, spec: dict, *, actor: str = "user") -> dict:
        if not spec.get("name") or not spec.get("steps"):
            raise ValueError("workflow requires name and steps")
        return self.entities.create("workflow", {
            "version": "1.0.0", "status": "active", "builtin": False,
            "trigger": spec.get("trigger", "manual"),
            "conditions": spec.get("conditions", []),
            "risk": spec.get("risk", "internal"),
            "permissions": spec.get("permissions", ["READ_DATA", "WRITE_DATA"]),
            "approval_policy": spec.get("approval_policy", "require"),
            "retry_policy": spec.get("retry_policy", {"max": 1}),
            "timeout_seconds": spec.get("timeout_seconds", 30),
            "notification_policy": spec.get("notification_policy", "digest-ok"),
            **{k: v for k, v in spec.items() if k not in {
                "trigger", "conditions", "risk", "permissions", "approval_policy",
                "retry_policy", "timeout_seconds", "notification_policy"}},
        }, actor=actor, idempotency_key=spec.get("idempotency_key"))

    def run(self, workflow_id: str, *, approved: bool = False, actor: str = "user",
            approval_id: str | None = None, idempotency_key: str | None = None) -> dict:
        wf = self.get(workflow_id)
        if not wf:
            raise KeyError(workflow_id)
        if wf.get("status") != "active":
            return {"status": "disabled", "workflow": wf.get("name")}

        risk_name = wf.get("risk", "internal")
        policy = self.permissions.authorize(
            f"workflow:{wf.get('name')}", level=risk_name,
            approved=approved, actor=actor,
            result={"workflow_id": wf["id"], "approval_id": approval_id})
        if not policy["allowed"]:
            approval = self.permissions.request_approval(
                f"workflow:{wf.get('name')}", risk=policy["risk"],
                permission=policy["permission"], reason=policy["reason"],
                payload={"approval_kind": "workflow", "reference": workflow_id,
                         "workflow_id": wf["id"], "name": wf.get("name"),
                         "steps": wf.get("steps")},
                context={"actor": actor})
            self._record_run(wf, "approval_required", [], idempotency_key)
            return {"status": "approval_required", "workflow": wf.get("name"),
                    "policy": policy, "approval": approval,
                    "explanation": "risk level 2+ actions need your explicit approval "
                                   "before anything external happens"}

        run_id = uid("run")
        steps_out, error = [], None
        started = time.monotonic()
        timeout = float(wf.get("timeout_seconds") or 30)
        self.events.emit("workflow.started", {"workflow_id": wf["id"],
                                              "run_id": run_id}, actor=actor)
        for step in wf.get("steps", []):
            if time.monotonic() - started > timeout:
                error = f"timeout after {timeout}s"
                break
            try:
                steps_out.append(self._execute_step(step, wf, actor=actor, approved=True))
            except Exception as exc:
                error = f"step {step.get('action')} failed: {exc}"
                break
        status = "failed" if error else "completed"
        self.events.emit(f"workflow.{status}", {"workflow_id": wf["id"], "run_id": run_id,
                                                "error": error}, actor=actor)
        run = self._record_run(wf, status, steps_out, idempotency_key, error, run_id)
        return {"status": status, "workflow": wf.get("name"), "run_id": run_id,
                "steps": steps_out, "error": error, "verified": status == "completed",
                "policy": {k: policy[k] for k in ("risk", "permission", "allowed")}}

    # ------------------------------------------------------------------ steps
    def _execute_step(self, step: dict, wf: dict, *, actor: str, approved: bool) -> dict:
        action = step.get("action")
        if action == "daily_plan":
            return {"action": action, "result": self.planner.daily_plan()}
        if action == "evening_summary":
            return {"action": action, "result": {"state": self.state.summary()}}
        if action == "weekly_review":
            return {"action": action, "result": self.planner.weekly_review()}
        if action == "monthly_review":
            return {"action": action, "result": self.planner.monthly_review()}
        if action == "relationship_scan":
            needs = self.state.compute()["relationship_needs"]
            return {"action": action, "result": {"needing_attention": len(needs),
                    "people": [p.get("name") for p in needs[:5]]}}
        if action == "research_scan":
            research = self.entities.list("research", limit=20)
            questions = self.entities.list("question", limit=20)
            open_q = [q for q in questions if q.get("status") not in {"done", "answered"}]
            return {"action": action, "result": {"research_items": len(research),
                    "open_questions": len(open_q),
                    "advice": "continue from existing findings before starting new threads"}}
        if action == "open_loop_scan":
            snap = self.state.compute()
            return {"action": action, "result": {"open_loops": snap["open_loops"],
                    "life_debt": snap["life_debt"]}}
        if action == "idea_clusters":
            return {"action": action, "result": self._idea_clusters()}
        if action == "project_health":
            projects = self.entities.list("project", limit=50)
            return {"action": action, "result": {
                "projects": [{"name": p.get("name") or p.get("title"),
                              **self.insights.project_health(p)} for p in projects]}}
        if action == "learning_scan":
            learning = self.entities.list("learning", limit=50)
            return {"action": action, "result": {"objectives": len(learning)}}
        if action == "inbox_scan":
            return {"action": action, "result": self._inbox_scan()}
        if action == "notify":
            note = self.notifications.create(
                category=step.get("category", "Useful"), title=step.get("title", "Update"),
                body=step.get("body"), why=f"workflow {wf.get('name')} notification policy: "
                f"{wf.get('notification_policy')}")
            return {"action": action, "result": {"notification_id": note["id"]}}
        if action == "send_message":
            channel = step.get("channel", "telegram")
            if channel == "draft-only":
                draft = self.notifications.create(
                    category="Important",
                    title=step.get("title", "Draft ready for your review"),
                    body=step.get("text", "A drafted touchpoint is waiting — review, edit, then send."),
                    why="relationship-agent policy: drafts only, nothing is sent without you")
                return {"action": action, "result": {"mode": "draft-only",
                                                     "draft_notification_id": draft["id"],
                                                     "sent": False,
                                                     "note": "no message was sent; draft awaits your approval"}}
            result = self.tools.execute(channel, "write", {"text": step.get("text", "hello")},
                                        actor=actor, approved=approved)
            return {"action": action, "result": result}
        raise ValueError(f"unknown workflow action: {action}")

    def _idea_clusters(self) -> dict:
        ideas = self.entities.list("idea", limit=100)
        clusters: dict[str, list] = {}
        for idea in ideas:
            tokens = {t for t in str(idea.get("title", "")).lower().split() if len(t) > 4}
            placed = False
            for key, members in clusters.items():
                key_tokens = set(key.split("|"))
                if tokens & key_tokens:
                    members.append(idea.get("title"))
                    placed = True
                    break
            if not placed:
                clusters["|".join(sorted(tokens)[:2]) or idea["id"]] = [idea.get("title")]
        groups = [v for v in clusters.values() if len(v) > 1]
        return {"ideas": len(ideas), "collision_clusters": groups,
                "advice": "clusters share key concepts — consider merging or linking them"}

    def _inbox_scan(self) -> dict:
        messages = self.entities.list("message", limit=50) + \
                   self.entities.list("email", limit=50)
        extracted = []
        for msg in messages:
            text = str(msg.get("body") or msg.get("text") or "")
            if any(k in text.lower() for k in ("deadline", "by friday", "due", "promise")):
                extracted.append({"message": msg["id"], "detected": "possible commitment/deadline",
                                  "needs": "user confirmation before becoming a commitment entity"})
        return {"scanned": len(messages), "candidates": extracted,
                "guardrail": "uncertain extractions stay suggestions until confirmed"}

    def _record_run(self, wf, status, steps, idempotency_key, error=None, run_id=None):
        from .util import dumps
        run_id = run_id or uid("run")
        if idempotency_key:
            existing = self.entities.db.one(
                "SELECT id FROM workflow_runs WHERE idempotency_key=?", (idempotency_key,))
            if existing:
                return {"id": existing["id"], "deduplicated": True}
        self.entities.db.execute(
            "INSERT INTO workflow_runs(id,workflow_id,status,steps,error,started_at,finished_at,idempotency_key)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (run_id, wf["id"], status, dumps(steps), error, iso(), iso(), idempotency_key))
        return {"id": run_id, "status": status}

    def runs(self, limit: int = 50) -> list[dict]:
        from .util import loads
        rows = self.entities.db.query(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (int(limit),))
        return [{"id": r["id"], "workflow_id": r["workflow_id"], "status": r["status"],
                 "steps": loads(r["steps"]), "error": r["error"],
                 "started_at": r["started_at"], "finished_at": r["finished_at"]} for r in rows]
