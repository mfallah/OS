"""Backwards-compatible shim for the v1 core module.

The real implementation lives in the `core` package (v2). This shim keeps the
v1 import contract working:

    from personal_os_core import PersonalOS, Orchestrator, WorkflowEngine

v1 constructor shapes are preserved: `PersonalOS(path)`, `Orchestrator(os)`,
`WorkflowEngine(os)`, including the old ad-hoc `run({...risk...})` call shape
and `plan(request)`.
"""
from __future__ import annotations

from core.app import PersonalOS as _PersonalOS
from core.orchestrator import Orchestrator as _Orchestrator
from core.permissions import PERMISSIONS, RISK
from core.context import ContextEngine  # noqa: F401


class PersonalOS(_PersonalOS):
    """v1-compatible facade over the v2 subsystem wiring."""

    def plan(self, request: str) -> dict:
        return Orchestrator(self).plan(request)


class Orchestrator(_Orchestrator):
    """v1 `Orchestrator(os)` constructor + `plan()` method."""

    def __init__(self, os_app: PersonalOS):
        super().__init__(os_app.entities, os_app.context, os_app.permissions,
                         os_app.agents, os_app.skills, os_app.tools,
                         os_app.memory_store, os_app.events, os_app.planner,
                         os_app.insights)
        self._app = os_app

    def plan(self, request: str) -> dict:
        intent = self.detect_intent(request)
        ctx = self._app.context.retrieve(request)
        return {"intent": intent["intent"], "request": request, "context": ctx,
                "risk": {0: "informational", 1: "internal",
                         2: "external", 3: "sensitive"}[intent["base_risk"]],
                "agent": self._app.agents.select_for(intent["intent"]).get("name"),
                "next": "provider decision required" if intent["base_risk"] == 0
                        else "approval check required",
                "verification": ["validate schema", "check permissions", "audit action"]}


class WorkflowEngine:
    """v1 `WorkflowEngine(os).run(dict, approved=...)` ad-hoc call shape."""

    def __init__(self, os_app: PersonalOS):
        self._app = os_app

    def run(self, workflow: dict, *, approved: bool = False, actor: str = "user") -> dict:
        if "steps" in workflow or self._app.workflows.get(workflow.get("name", "")):
            return self._app.workflows.run(workflow.get("id") or workflow.get("name"),
                                           approved=approved, actor=actor)
        policy = self._app.permissions.authorize(
            workflow.get("action", "workflow"), level=workflow.get("risk", "informational"),
            approved=approved, actor=actor,
            result={"name": workflow.get("name", "workflow"), "ad_hoc": True})
        return {"allowed": policy["allowed"], "policy": policy,
                "status": "executed" if policy["allowed"] else "approval_required"}


__all__ = ["PersonalOS", "Orchestrator", "WorkflowEngine", "ContextEngine",
           "RISK", "PERMISSIONS"]
