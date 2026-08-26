"""PersonalOS facade: wires every subsystem into one service object.

Single entry point for the local server, the Vercel function and the test
suite, so all three exercise identical behavior. The facade also exposes the
legacy v1 method surface (create/update/list/get/link/neighbors/remember/
memories/event/audit/authorize/context/cognitive_load/search/count/close)
for backwards compatibility with earlier code and tests.
"""
from __future__ import annotations

from .agents import AgentRegistry
from .capture import CaptureService
from .context import ContextEngine
from .db import Database
from .entities import EntityStore
from .events import EventBus
from .graph import Graph
from .insights import InsightEngine
from .memory import MemoryStore
from .notifications import NotificationCenter
from .orchestrator import Orchestrator
from .ownership import DataOwnership
from .permissions import PERMISSIONS, RISK, PermissionEngine
from .planning import Planner
from .search import UniversalSearch
from .security import Authenticator, RateLimiter
from .seed import seed as seed_if_empty
from .skills import SkillRegistry
from .state import PersonalState
from .tools import ToolRegistry
from .workflows import WorkflowEngine


class PersonalOS:
    def __init__(self, path: str | None = None, *, auto_seed: bool = True):
        self.db = Database(path)
        self.events = EventBus(self.db)
        self.entities = EntityStore(self.db, self.events)
        self.graph = Graph(self.db, self.entities, self.events)
        self.memory_store = MemoryStore(self.db, self.events)
        self.permissions = PermissionEngine(self.db, self.events)
        self.notifications = NotificationCenter(self.db, self.events)
        self.state = PersonalState(self.entities, self.events, self.notifications)
        self.insights = InsightEngine(self.entities, self.events, self.state)
        self.planner = Planner(self.entities, self.events, self.state, self.insights)
        self.context = ContextEngine(self.entities, self.graph, self.memory_store,
                                     self.state, {})
        self.tools = ToolRegistry(self.permissions, self.events)
        self.agents = AgentRegistry(self.entities)
        self.skills = SkillRegistry(self.entities, self.permissions)
        self.workflows = WorkflowEngine(self.entities, self.events, self.permissions,
                                        self.tools, self.state, self.planner,
                                        self.insights, self.notifications,
                                        self.graph, self.memory_store)
        self.orchestrator = Orchestrator(self.entities, self.context, self.permissions,
                                         self.agents, self.skills, self.tools,
                                         self.memory_store, self.events, self.planner,
                                         self.insights)
        self.capture_service = CaptureService(self.entities, self.graph,
                                              self.memory_store, self.events)
        self.search_engine = UniversalSearch(self.entities, self.graph, self.memory_store)
        self.ownership = DataOwnership(self.db, self.entities, self.memory_store,
                                       self.events, self.permissions)
        self.rate_limiter = RateLimiter(self.db)
        self.auth = Authenticator()
        if auto_seed:
            seed_if_empty(self)
        self._wire_event_subscribers()

    # ------------------------------------------------------- event reactions
    def _wire_event_subscribers(self):
        """task.updated → derived task.completed / task.deferred signals."""
        def completion_or_defer(event):
            patch_keys = event["payload"].get("patch_keys") or []
            ent = self.entities.get(event["payload"].get("entity_id", ""))
            if not ent:
                return
            if "status" in patch_keys and ent.get("status") in {"done", "completed"}:
                self.events.emit("task.completed",
                                 {"entity_id": ent["id"], "title": ent.get("title")},
                                 actor=event["actor"])
            if "due" in patch_keys:
                self.events.emit("task.deferred",
                                 {"entity_id": ent["id"], "title": ent.get("title")},
                                 actor=event["actor"])
        self.events.subscribe("task.updated", completion_or_defer)

    # ----------------------------------------------------- aggregated state
    def ui_state(self) -> dict:
        snap = self.state.compute()
        projects = snap["projects"]
        for p in projects:
            p["health"] = self.insights.project_health(p)
        insights = self.insights.generate()
        plan = self.planner.daily_plan()
        return {
            "date": snap["date"],
            "constitution": (self.entities.list("constitution", limit=1) or [None])[0],
            "objective": self._main_objective(snap, plan),
            "today_plan": plan,
            "tasks": self.entities.list("task", limit=200),
            "projects": projects,
            "people": self.entities.list("person", limit=200),
            "ideas": self.entities.list("idea", limit=200),
            "research": self.entities.list("research", limit=100),
            "questions": self.entities.list("question", limit=100),
            "decisions": self.entities.list("decision", limit=100),
            "learning": self.entities.list("learning", limit=100),
            "calendar": self.entities.list("calendar_event", limit=100),
            "goals": self.entities.list("goal", limit=100),
            "insights": insights,
            "recent_changes": self.events.list(limit=12),
            "pending_decisions": snap["unresolved_decisions"][:3],
            "relationship_attention": snap["relationship_needs"][:4],
            "state": snap,
            "recommended_next_action": self._recommendation(snap, plan, insights),
            "pending_approvals": self.permissions.pending_approvals(),
        }

    def _main_objective(self, snap, plan) -> dict:
        if plan["items"]:
            top = plan["items"][0]
            return {"title": top["title"], "why": top["why"],
                    "task_id": top["task_id"], "estimate": top["estimate"]}
        goals = self.entities.list("goal", limit=1)
        return {"title": goals[0]["title"] if goals else "Define your main objective",
                "why": "no scheduled work — pick one meaningful move", "estimate": 30}

    @staticmethod
    def _recommendation(snap, plan, insights) -> dict:
        risks = [i for i in insights if i["kind"] == "Risk"]
        if snap["workload"]["overdue"]:
            return {"action": "Clear overdue work first",
                    "reason": "overdue items weigh most in your cognitive-load model"}
        if risks:
            return {"action": risks[0]["action"], "reason": risks[0]["body"]}
        if plan["items"]:
            return {"action": f"Start: {plan['items'][0]['title']}",
                    "reason": "top of your capacity-aware plan"}
        return {"action": "Take a real break", "reason": "capacity is clear — protect it"}

    # ---------------------------------------------------- legacy v1 surface
    def count(self, kind=None):
        return self.entities.count(kind)

    def create(self, kind, data, *, actor="user", idempotency_key=None):
        return self.entities.create(kind, data, actor=actor,
                                    idempotency_key=idempotency_key)

    def update(self, entity_id, patch, *, actor="user"):
        return self.entities.update(entity_id, patch, actor=actor)

    def list(self, kind=None, limit=200):
        return self.entities.list(kind, limit)

    def get(self, entity_id):
        return self.entities.get(entity_id)

    def link(self, source, relation, target):
        return self.graph.link(source, relation, target)

    def neighbors(self, entity_id, relation=None):
        return self.graph.neighbors(entity_id, relation)

    def remember(self, category, content, **kwargs):
        return self.memory_store.remember(category, content, **kwargs)

    def memory(self, memory_id):
        return self.memory_store.get(memory_id)

    def memories(self, category=None, query=None, limit=30):
        return self.memory_store.list(category, query, limit)

    def event(self, typ, payload, *, actor="system", idempotency_key=None):
        return self.events.emit(typ, payload, actor=actor,
                                idempotency_key=idempotency_key)

    def audit(self, action, policy, **kwargs):
        if not isinstance(policy, dict):
            policy = {"permission": getattr(policy, "permission", "READ_DATA"),
                      "risk": getattr(policy, "risk", 0),
                      "approved": getattr(policy, "approved", False),
                      "allowed": getattr(policy, "approved", False)}
        return self.permissions.audit(action, policy, **kwargs)

    def authorize(self, action, *, level="informational", approved=False, permissions=None):
        return self.permissions.authorize(action, level=level, approved=approved)

    def context(self, query="", *, kinds=None, limit=20):
        return self.context.retrieve(query, kinds=kinds, limit=limit)

    def cognitive_load(self):
        return self.state.compute()["cognitive_load"]

    def search(self, query, limit=30):
        return self.search_engine.search(query, limit=limit)

    def close(self):
        self.db.close()
