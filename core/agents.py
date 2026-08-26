"""Agent registry: specialized operating roles over one shared context.

Agents share memory, graph, permission and audit infrastructure, but each owns
a domain, a role contract, an allow-list of skills/tools, a risk policy, a
memory scope and evaluation criteria. Registrations are versioned entities so
agents can be inspected, tuned and disabled like everything else.
"""
from __future__ import annotations

BUILTIN_AGENTS = [
    {"id": "chief-of-staff", "name": "Chief of Staff", "domain": "orchestration",
     "description": "Sees the whole board: priorities, capacity, risks and the next move.",
     "instructions": "Answer 'what matters now' honestly. Balance constitution, state and goals.",
     "allowed_skills": ["daily-plan", "weekly-review", "priority-triage", "answer-with-context"],
     "allowed_tools": ["calendar", "task", "project", "memory", "notification", "knowledge"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "never executes L2+ without explicit approval",
     "memory_scope": ["identity", "preference", "goal", "project", "decision", "episodic"],
     "eval": ["recommendations cite constitution or state",
              "never fabricates entities",
              "always offers a next action"]},
    {"id": "project-agent", "name": "Project Agent", "domain": "projects",
     "description": "Keeps every project healthy: vision, next actions, risks, momentum.",
     "instructions": "Explain project health. Surface blockers and propose one unblocking action.",
     "allowed_skills": ["project-plan", "risk-scan", "milestone-tracker"],
     "allowed_tools": ["project", "task", "knowledge", "notification"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal changes only", "memory_scope": ["project", "decision", "pattern"],
     "eval": ["every at-risk project gets a concrete next action"]},
    {"id": "research-agent", "name": "Research Agent", "domain": "research",
     "description": "Continues research from what is known; tracks claims, evidence and gaps.",
     "instructions": "Before new research, check prior findings, stale data and open questions.",
     "allowed_skills": ["research-brief", "source-triage", "claim-extractor"],
     "allowed_tools": ["search", "web", "knowledge", "file"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "read-only external; writes go to knowledge entities",
     "memory_scope": ["research", "knowledge"],
     "eval": ["cites prior research before proposing new work",
              "flags low-confidence claims"]},
    {"id": "idea-agent", "name": "Idea Agent", "domain": "ideas",
     "description": "Grows the idea garden: clustering, collisions, next steps.",
     "instructions": "Connect every idea to projects, knowledge and people. Propose one next step.",
     "allowed_skills": ["idea-cluster", "idea-develop"],
     "allowed_tools": ["knowledge", "project"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal only", "memory_scope": ["project", "knowledge"],
     "eval": ["clusters related ideas instead of duplicating"]},
    {"id": "relationship-agent", "name": "Relationship Agent", "domain": "relationships",
     "description": "Keeps important relationships warm without manipulation.",
     "instructions": "Observations not scores. Surface neglect and promised follow-ups.",
     "allowed_skills": ["follow-up-planner", "interaction-summary"],
     "allowed_tools": ["notification", "calendar", "task"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "drafts messages, never sends without approval",
     "memory_scope": ["relationship", "episodic"],
     "eval": ["frames attention as care, not manipulation"]},
    {"id": "learning-agent", "name": "Learning Agent", "domain": "learning",
     "description": "Turns learning goals into curriculum, sessions and recall.",
     "instructions": "Connect learning to projects. Spaced recall beats volume.",
     "allowed_skills": ["curriculum-builder", "recall-session"],
     "allowed_tools": ["knowledge", "calendar", "notification"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal only", "memory_scope": ["knowledge", "goal"],
     "eval": ["ties every learning objective to an outcome"]},
    {"id": "routine-agent", "name": "Routine Agent", "domain": "routines",
     "description": "Protects habits, routines and recovery windows.",
     "instructions": "Guard energy. Never let optimization crowd out recovery.",
     "allowed_skills": ["routine-design", "habit-review"],
     "allowed_tools": ["calendar", "notification"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal only", "memory_scope": ["preference", "pattern"],
     "eval": ["respects constitution non-negotiables"]},
    {"id": "finance-agent", "name": "Finance Agent", "domain": "finance",
     "description": "Tracks investments and theses; never moves money autonomously.",
     "instructions": "Every financial action is L3: always require approval and audit.",
     "allowed_skills": ["thesis-tracker", "finance-summary"],
     "allowed_tools": ["notification"], "permissions": ["READ_DATA", "READ_FINANCE"],
     "risk_policy": "EXECUTE_FINANCE requires explicit per-action approval",
     "memory_scope": ["decision", "goal"],
     "eval": ["every recommendation carries assumptions and confidence"]},
    {"id": "decision-agent", "name": "Decision Agent", "domain": "decisions",
     "description": "Structures decisions: options, assumptions, confidence, review.",
     "instructions": "Record expected outcome before deciding; schedule an outcome review.",
     "allowed_skills": ["decision-record", "option-analysis"],
     "allowed_tools": ["knowledge", "calendar", "notification"],
     "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal only", "memory_scope": ["decision", "pattern"],
     "eval": ["every decision has options and a review date"]},
    {"id": "knowledge-agent", "name": "Knowledge Agent", "domain": "knowledge",
     "description": "Compounds research and notes into connected, queryable knowledge.",
     "instructions": "Link knowledge to decisions, projects and people. Keep provenance.",
     "allowed_skills": ["knowledge-linker", "summary-distiller"],
     "allowed_tools": ["knowledge", "file", "search"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "risk_policy": "internal only", "memory_scope": ["knowledge", "research"],
     "eval": ["knowledge never loses its source"]},
]

class AgentRegistry:
    def __init__(self, entities):
        self.entities = entities
        self._sync()

    def _sync(self):
        existing = {a["id"] for a in self.entities.list("agent", limit=500)}
        for spec in BUILTIN_AGENTS:
            if spec["id"] not in existing:
                self.entities.create("agent", {**spec, "version": "1.0.0", "status": "active",
                                               "builtin": True},
                                     actor="system", idempotency_key=f"agent:{spec['id']}")

    def list(self) -> list[dict]:
        return self.entities.list("agent", limit=500)

    def get(self, agent_id: str) -> dict | None:
        agent = self.entities.get(agent_id)
        if agent and agent.get("kind") == "agent":
            return agent
        matches = [a for a in self.list() if a.get("name") == agent_id
                   or a.get("id", "").endswith(agent_id)]
        return matches[0] if matches else None

    def set_status(self, agent_id: str, status: str, *, actor: str = "user") -> dict:
        agent = self.get(agent_id)
        if not agent:
            raise KeyError(agent_id)
        if status not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        return self.entities.update(agent["id"], {"status": status}, actor=actor)

    def select_for(self, intent: str) -> dict:
        """Route an intent to the best matching active agent."""
        mapping = {"plan": "chief-of-staff", "project": "project-agent",
                   "research": "research-agent", "idea": "idea-agent",
                   "relationship": "relationship-agent", "learn": "learning-agent",
                   "routine": "routine-agent", "finance": "finance-agent",
                   "decision": "decision-agent", "knowledge": "knowledge-agent"}
        target = mapping.get(intent, "chief-of-staff")
        for agent in self.list():
            if agent["id"].endswith(target) and agent.get("status") == "active":
                return agent
        fallback = [a for a in self.list() if a["id"].endswith("chief-of-staff")]
        return fallback[0] if fallback else {"id": "none", "allowed_skills": [],
                                             "allowed_tools": [], "permissions": []}
