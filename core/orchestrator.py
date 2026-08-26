"""AI orchestrator: the full loop, provider-neutral.

User input -> intent detection -> context resolution -> risk classification ->
planning -> agent selection -> skill selection -> tool selection -> execution
-> verification -> memory update -> audit -> user feedback.

Prompts are composed in layers (identity, safety, role, skill, constitution,
memory, state, task, contract) — never one giant prompt for everything. The
model never sees chain-of-thought storage; only decision summaries and reasons
are persisted.
"""
from __future__ import annotations

from .providers import get_provider

# Order matters: external/sensitive/destructive intents are checked first so a
# message like "send an email about the research" is risk-classified, not
# treated as harmless research.
INTENT_RULES = [
    (("pay", "invest", "transfer", "پرداخت", "سرمایه", "خرید"), "sensitive-action", 3),
    (("send", "email", "message", "forward", "ارسال", "پیام", "ایمیل", "بفرست"), "external-action", 2),
    (("delete", "remove", "حذف", "پاک کن"), "destructive", 2),
    (("plan", "today", "امروز", "برنامه", "روز"), "plan", 1),
    (("research", "تحقیق", "پژوهش"), "research", 1),
    (("idea", "ایده"), "idea", 1),
    (("decide", "decision", "تصمیم"), "decision", 1),
    (("learn", "یادگیری"), "learn", 1),
    (("what matters", "status", "وضعیت"), "status", 0),
]

SAFETY_POLICY = {
    "rules": ["never delete, send or modify important data without confirmation",
              "risk level 2+ requires explicit user approval",
              "recommendations must be explainable from constitution, memory or state",
              "uncertain assumptions never become permanent identity facts",
              "no chain-of-thought is stored; only decisions with reasons"],
}

class Orchestrator:
    def __init__(self, entities, context, permissions, agents, skills, tools,
                 memory, events, planner, insights):
        self.entities = entities
        self.context = context
        self.permissions = permissions
        self.agents = agents
        self.skills = skills
        self.tools = tools
        self.memory = memory
        self.events = events
        self.planner = planner
        self.insights = insights

    # ---------------------------------------------------------------- intents
    def detect_intent(self, text: str) -> dict:
        lowered = (text or "").lower()
        for keys, intent, base_risk in INTENT_RULES:
            if any(k in lowered for k in keys):
                return {"intent": intent, "base_risk": base_risk,
                        "confidence": 0.75,
                        "reason": f"matched intent rules for '{intent}'"}
        return {"intent": "question", "base_risk": 0, "confidence": 0.5,
                "reason": "no action keywords; treated as an informational question"}

    # ------------------------------------------------------------------- run
    def handle(self, message: str, *, focal_entity: str | None = None,
               actor: str = "user", approved: bool = False) -> dict:
        intent = self.detect_intent(message)
        agent = self.agents.select_for(intent["intent"])
        ctx = self.context.retrieve(message, focal_entity=focal_entity)
        risk = intent["base_risk"]
        skill_names = agent.get("allowed_skills", [])[:3]
        tool_names = agent.get("allowed_tools", [])[:4]

        plan = {"steps": ["detect intent", "resolve context", "classify risk",
                          "select agent/skills/tools", "execute", "verify",
                          "update memory", "audit", "respond"],
                "intent": intent, "agent": agent.get("name"), "skills": skill_names,
                "tools": tool_names, "risk": risk}

        policy = self.permissions.authorize(
            f"orchestrator:{intent['intent']}", level=risk, approved=approved,
            actor=actor, agent=agent.get("id"),
            result={"intent": intent["intent"]})

        if not policy["allowed"]:
            approval = self.permissions.request_approval(
                f"orchestrator:{intent['intent']}", risk=policy["risk"],
                permission=policy["permission"], reason=policy["reason"],
                payload={"message": message[:300], "agent": agent.get("name")},
                context={"intent": intent})
            return {"status": "approval_required", "plan": plan, "policy": policy,
                    "approval": approval, "answer":
                    "This request involves an external or sensitive action. "
                    "Review the approval request and confirm before I proceed.",
                    "explanation": policy["reason"]}

        outcome = self._execute(intent["intent"], message, ctx, agent)
        answer = outcome["answer"]
        draft = outcome.get("draft")

        prompt_layers = self._prompt_layers(agent, ctx, message, draft)
        provider = get_provider()
        completion = provider.complete(prompt_layers)
        if provider.name != "demo":
            answer = completion["text"]

        memory_note = self.memory.remember(
            "episodic",
            f"user asked about '{message[:120]}' → intent {intent['intent']}",
            confidence=0.8, source="conversation", created_by=agent.get("id", "system"),
            importance=3, why="kept briefly to improve follow-up continuity")
        self.events.emit("insight.created", {"kind": "orchestration",
                                             "intent": intent["intent"]}, actor=agent.get("id"))

        return {"status": "ok", "answer": answer, "plan": plan,
                "provider": completion.get("provider"), "model": completion.get("model"),
                "context_summary": {
                    "entities_used": len(ctx["selected_entities"]),
                    "memories_used": len(ctx["selected_memories"]),
                    "confidence": ctx["confidence"],
                    "reasons": [e.get("retrieval_reason") for e in
                                ctx["selected_entities"][:3]]},
                "suggestions": outcome.get("suggestions", []),
                "verification": outcome.get("verification", ["no side effects to verify"]),
                "memory_trace": {"memory_id": memory_note["id"],
                                 "why": memory_note["why"]},
                "policy": {k: policy[k] for k in ("risk", "permission", "allowed")}}

    # -------------------------------------------------------------- execution
    def _execute(self, intent: str, message: str, ctx: dict, agent: dict) -> dict:
        if intent == "plan":
            plan = self.planner.daily_plan()
            return {"answer": self._render_plan(plan),
                    "suggestions": plan.get("deliberately_skipped", [])[:2],
                    "verification": [f"{len(plan['items'])} items scheduled, "
                                     f"slack {plan['slack_hours']}h preserved"],
                    "draft": None}
        if intent == "status":
            snap = ctx["personal_state"]
            insights = self.insights.generate()[:3]
            lines = [f"Load {snap['cognitive_load']}/100 ({snap['load_band']}), "
                     f"life debt {snap['life_debt']}, "
                     f"{snap['open_tasks']} open tasks ({snap['overdue']} overdue)."]
            return {"answer": lines[0] + " Top signals: " + "; ".join(i["title"] for i in insights)
                              if insights else lines[0],
                    "verification": ["state recomputed live from entities and events"]}
        if intent == "research":
            researches = self.entities.list("research", limit=5)
            questions = [q for q in self.entities.list("question", limit=20)
                         if q.get("status") not in {"done", "answered"}]
            bodies = [f"you already have {len(researches)} research threads and "
                      f"{len(questions)} open questions. Continue from the newest open "
                      "question before starting a new thread."]
            return {"answer": "Before new research: " + bodies[0],
                    "suggestions": [{"task": f"resolve question: {q.get('title') or q.get('question')}"}
                                    for q in questions[:3]],
                    "verification": ["prior research checked first"]}
        top = ctx["selected_entities"][:3]
        memories = ctx["selected_memories"][:2]
        answer_bits = []
        if top:
            answer_bits.append("Most relevant right now: " + "; ".join(
                f"{e.get('title') or e.get('name')} ({e['kind']})" for e in top) + ".")
        if memories:
            answer_bits.append("Remembered: " + "; ".join(m["content"][:80] for m in memories))
        if not answer_bits:
            answer_bits.append("I don't have much context on that yet. Capture it and "
                               "I'll connect it to your projects and goals.")
        return {"answer": " ".join(answer_bits),
                "verification": ["answer grounded in retrieved context only"]}

    def _render_plan(self, plan: dict) -> str:
        items = "; ".join(f"«{i['title']}» ({i['estimate']}min, because {i['why']})"
                          for i in plan["items"][:4])
        return (f"Today's plan fills {plan['planned_minutes']} minutes of "
                f"{plan['capacity_hours']}h capacity, leaving {plan['slack_hours']}h slack. "
                f"In order: {items or 'nothing pressing — keep the day open'}.")

    # ---------------------------------------------------------------- prompt
    def _prompt_layers(self, agent: dict, ctx: dict, message: str, draft) -> dict:
        return {
            "system_identity": {"name": "myos", "role": "personal chief of staff",
                                "tone": "calm, precise, honest"},
            "safety_policy": SAFETY_POLICY["rules"],
            "agent_role": {"name": agent.get("name"), "domain": agent.get("domain"),
                           "instructions": agent.get("instructions")},
            "skill_instructions": [self.skills.get(s).get("instructions")
                                   for s in (agent.get("allowed_skills") or [])[:3]
                                   if self.skills.get(s)],
            "constitution": ctx["constitution_fragments"],
            "memories": [{"content": m["content"], "confidence": m["confidence"]}
                         for m in ctx["selected_memories"][:5]],
            "personal_state": ctx["personal_state"],
            "task_context": {"request": message,
                             "entities": [{"id": e["id"], "kind": e["kind"],
                                           "title": e.get("title") or e.get("name")}
                                          for e in ctx["selected_entities"][:6]],
                             "draft": draft},
            "output_contract": {"format": "short paragraphs",
                                "must_include": ["answer", "reason", "next action"],
                                "never_include": ["chain-of-thought", "raw tool logs"]},
        }
