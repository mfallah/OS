"""First-run seed: a realistic starter graph so the OS is useful immediately.

Idempotent by entity idempotency keys; only applied when the entity table is
empty. All items are ordinary entities the user can edit or delete.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

def _days_ago(n: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=n)).isoformat()

def seed(os_app) -> None:
    """Runs exactly once per database: tracked by a meta flag rather than
    entity counts, because builtin agent/skill/workflow registries also
    populate the entity table before the first user writes anything."""
    if os_app.db.one("SELECT value FROM meta WHERE key='seed_done'"):
        return
    os_app.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('seed_done','1')")
    e = os_app.entities
    today = datetime.now(UTC).date()

    constitution = e.create("constitution", {
        "title": "Personal constitution",
        "values": ["Clarity", "Craft", "Relationships", "Health"],
        "principles": ["Protect attention", "Choose meaningful progress",
                       "Explain before you automate"],
        "long_term_vision": "A calm, intelligent operating system for life.",
        "non_negotiables": ["Protect deep work", "Leave room for recovery",
                            "Family before notifications"],
        "risk_tolerance": "moderate", "planning_style": "capacity-aware",
        "communication_style": "concise and warm",
        "priorities": ["Ship Ourex core", "Keep research practice alive",
                       "Stay close to family"],
        "active_project_limit": 3,
        "notification_preferences": {"daily_budget": 12, "quiet_hours": ["21:00", "08:00"]},
    }, actor="system", idempotency_key="seed:constitution")

    goal_year = e.create("goal", {
        "title": "Build a calm, intelligent Personal OS", "horizon": "year",
        "status": "active", "priority": 10, "horizon_rank": 1,
    }, actor="system", idempotency_key="seed:goal:ourex")
    goal_rel = e.create("goal", {
        "title": "Keep key relationships warm", "horizon": "quarter",
        "status": "active", "priority": 8,
    }, actor="system", idempotency_key="seed:goal:relationships")

    p_ourex = e.create("project", {
        "name": "Ourex", "description": "Personal OS architecture and product",
        "vision": "Chief of staff for life, not another dashboard",
        "status": "active", "progress": 55, "clarity": 80,
        "next_action": "Finish orchestrator boundary",
        "objectives": ["Real core entities+graph", "Approval-aware workflows"],
        "success_criteria": ["Daily use for planning", "Zero un-audited actions"],
    }, actor="system", idempotency_key="seed:project:ourex")
    p_learn = e.create("project", {
        "name": "Learning systems", "description": "A sustainable research practice",
        "status": "active", "progress": 30, "clarity": 65,
        "next_action": "Complete knowledge review",
    }, actor="system", idempotency_key="seed:project:learning")
    p_studio = e.create("project", {
        "name": "Home studio", "description": "A calm space for deep work",
        "status": "at-risk", "progress": 15, "clarity": 40,
    }, actor="system", idempotency_key="seed:project:studio")

    t1 = e.create("task", {"title": "Review Ourex architecture", "project": "Ourex",
                           "priority": "high", "status": "in-progress", "estimate": 90,
                           "due": str(today), "energy": "deep"},
                  actor="system", idempotency_key="seed:task:arch")
    t2 = e.create("task", {"title": "Send follow-up to Sara", "project": "Relationships",
                           "priority": "medium", "status": "open", "estimate": 15,
                           "due": str(today), "energy": "light"},
                  actor="system", idempotency_key="seed:task:sara")
    t3 = e.create("task", {"title": "Synthesize MCP research", "project": "Ourex",
                           "priority": "high", "status": "open", "estimate": 60,
                           "due": str(today + timedelta(days=1)), "energy": "deep"},
                  actor="system", idempotency_key="seed:task:mcp")
    t4 = e.create("task", {"title": "Book quarterly review", "project": "Personal",
                           "priority": "low", "status": "open", "estimate": 10,
                           "due": "This week", "energy": "light"},
                  actor="system", idempotency_key="seed:task:quarter")

    sara = e.create("person", {
        "name": "Sara Rahimi", "role": "Product collaborator", "importance": "high",
        "last_contact": _days_ago(9), "cadence_days": 7,
        "need": "Follow up on Ourex research",
        "communication_preference": "concise async",
    }, actor="system", idempotency_key="seed:person:sara")
    mina = e.create("person", {
        "name": "Mina", "role": "Family", "importance": "high",
        "last_contact": _days_ago(2), "need": "Meaningful weekly contact",
        "important_dates": [],
    }, actor="system", idempotency_key="seed:person:mina")

    i1 = e.create("idea", {
        "title": "MCP as a universal connection layer",
        "raw_capture": "Connect Ourex to external AI systems without coupling the core.",
        "summary": "MCP servers as pluggable tools behind the registry.",
        "status": "developing", "potential": "high", "origin": "reading MCP spec",
    }, actor="system", idempotency_key="seed:idea:mcp")
    i2 = e.create("idea", {
        "title": "Attention budget as a first-class resource",
        "raw_capture": "Plan time, energy and focus together instead of only hours.",
        "status": "captured", "potential": "medium",
    }, actor="system", idempotency_key="seed:idea:attention")

    r1 = e.create("research", {
        "title": "MCP architecture research",
        "objectives": ["Understand tool discovery and permission model"],
        "questions_open": ["How should MCP servers get scoped permissions?",
                           "What is the timeout/retry contract?"],
        "sources": 12, "claims": 4, "status": "active",
        "last_activity": _days_ago(1), "uncertainty": "medium",
    }, actor="system", idempotency_key="seed:research:mcp")
    q1 = e.create("question", {
        "title": "How should MCP servers get scoped permissions?",
        "status": "open", "research": "MCP architecture research",
    }, actor="system", idempotency_key="seed:q:mcp-perms")

    d1 = e.create("decision", {
        "title": "Adapter layer: generic bridge vs. per-integration contracts?",
        "context": "Telegram, Email, MCP each push the core in different directions.",
        "options": ["thin generic bridge", "explicit per-integration contract"],
        "assumptions": ["integrations stay outside the core"],
        "status": "open", "confidence": 0.6,
    }, actor="system", idempotency_key="seed:decision:adapters")

    e.create("learning", {
        "title": "Systems design for personal infrastructure", "status": "active",
        "curriculum": ["event-driven cores", "durable queues"],
        "resources": 3, "sessions_done": 2, "recall_due": str(today + timedelta(days=2)),
    }, actor="system", idempotency_key="seed:learning:sysdesign")

    e.create("habit", {"title": "Morning walk", "status": "active", "streak": 4,
                       "routine": "morning"}, actor="system",
             idempotency_key="seed:habit:walk")

    k1 = e.create("knowledge", {
        "title": "Event-driven cores keep interfaces replaceable",
        "summary": "Emit domain events on every mutation; integrations subscribe.",
        "source": "architecture practice", "confidence": 0.9,
    }, actor="system", idempotency_key="seed:knowledge:events")

    # ---- graph structure: User -> Goal -> Project -> Task -> Decision -> ...
    g = os_app.graph
    g.link(goal_year["id"], "supports", p_ourex["id"], actor="system")
    g.link(p_ourex["id"], "belongs_to", goal_year["id"], actor="system")
    for t in (t1, t3):
        g.link(t["id"], "supports", p_ourex["id"], actor="system")
    g.link(t2["id"], "supports", goal_rel["id"], actor="system")
    g.link(d1["id"], "depends_on", r1["id"], actor="system")
    g.link(q1["id"], "belongs_to", r1["id"], actor="system")
    g.link(i1["id"], "contributes_to", r1["id"], actor="system")
    g.link(k1["id"], "learned_from", r1["id"], actor="system")
    g.link(sara["id"], "connected_to", p_ourex["id"], actor="system")
    g.link(t2["id"], "follows_up", sara["id"], actor="system")
    g.link(p_studio["id"], "conflicts_with", constitution["id"], actor="system")

    os_app.memory_store.remember(
        "identity", "User is building Ourex, a calm AI-native personal OS",
        confidence=1.0, source="system", importance=9,
        provenance="seed", why="seeded identity fact from repository context")
    os_app.memory_store.remember(
        "preference", "Prefers concise explanations with explicit reasoning",
        confidence=0.9, source="system", importance=7, provenance="seed",
        why="guides answer style; correct it if wrong")
    os_app.memory_store.remember(
        "pattern", "Deep work lands best in morning focus windows",
        confidence=0.5, source="observed", importance=5,
        why="unconfirmed observation — confirm or correct in Memory governance")
