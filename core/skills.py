"""Skill registry: versioned, testable, composable units of capability.

A skill is a contract: identity, purpose, instructions, input/output schemas,
required knowledge, tool access, permissions, guardrails, evaluation criteria,
memory scope, version, changelog and status. Users create, edit, test,
enable/disable, duplicate, version, export(share) and delete skills. Skills can
compose: a composite skill runs its steps in order, threading outputs.
"""
from __future__ import annotations

from .util import iso, uid
from .permissions import PermissionEngine

BUILTIN_SKILLS = [
    {"name": "daily-plan", "domain": "planning",
     "purpose": "Produce a capacity-aware daily plan.",
     "instructions": "Fill at most 70% of capacity; respect energy and non-negotiables.",
     "input_schema": {"available_hours": "number?"}, "output_schema": {"plan": "list"},
     "tools": ["task", "calendar"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "guardrails": ["never overfill the day", "explain every item"], "eval": ["slack preserved"]},
    {"name": "weekly-review", "domain": "planning",
     "purpose": "Aggregate wins, stalls, risks and next-week strategy.",
     "instructions": "Use event history and current state; stay honest about misses.",
     "input_schema": {}, "output_schema": {"review": "object"},
     "tools": ["task", "project", "notification"], "permissions": ["READ_DATA"],
     "guardrails": ["no invented wins"], "eval": ["strategy addresses top risk"]},
    {"name": "answer-with-context", "domain": "general",
     "purpose": "Answer a question using retrieved context with citations.",
     "instructions": "Ground every claim in provided context; say 'I don't know' when thin.",
     "input_schema": {"question": "string"}, "output_schema": {"answer": "string"},
     "tools": ["knowledge", "memory"], "permissions": ["READ_DATA"],
     "guardrails": ["never fabricate entities"], "eval": ["claims cite context"]},
    {"name": "research-brief", "domain": "research",
     "purpose": "Consolidate research state before continuing.",
     "instructions": "List prior findings, stale data, open questions; continue from the edge.",
     "input_schema": {"topic": "string"}, "output_schema": {"brief": "object"},
     "tools": ["knowledge", "search"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "guardrails": ["prior research first"], "eval": ["open questions carried forward"]},
    {"name": "follow-up-planner", "domain": "relationships",
     "purpose": "Draft relationship touchpoints without manipulation.",
     "instructions": "Frame as care; reference real shared context; keep it optional.",
     "input_schema": {"person_id": "string"}, "output_schema": {"draft": "string"},
     "tools": ["notification", "task"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "guardrails": ["no pressure tactics", "drafts only"], "eval": ["person feels like a person"]},
    {"name": "decision-record", "domain": "decisions",
     "purpose": "Structure a decision with options, assumptions and review date.",
     "instructions": "Record expected outcome and confidence before recommending.",
     "input_schema": {"question": "string"}, "output_schema": {"decision": "object"},
     "tools": ["knowledge", "calendar"], "permissions": ["READ_DATA", "WRITE_DATA"],
     "guardrails": ["confidence is mandatory"], "eval": ["review date set"]},
]

class SkillRegistry:
    def __init__(self, entities, permissions: PermissionEngine):
        self.entities = entities
        self.permissions = permissions
        self._sync()

    def _sync(self):
        existing = {s.get("name") for s in self.entities.list("skill", limit=500)}
        for spec in BUILTIN_SKILLS:
            if spec["name"] not in existing:
                self.entities.create("skill", {**spec, "version": "1.0.0", "status": "active",
                                               "author": "system", "builtin": True,
                                               "changelog": [{"version": "1.0.0",
                                                              "at": iso(),
                                                              "note": "initial builtin"}],
                                               "composed_of": []},
                                     actor="system", idempotency_key=f"skill:{spec['name']}")

    def list(self) -> list[dict]:
        return self.entities.list("skill", limit=500)

    def get(self, skill_id: str) -> dict | None:
        skill = self.entities.get(skill_id)
        if skill and skill.get("kind") == "skill":
            return skill
        matches = [s for s in self.list() if s.get("name") == skill_id]
        return matches[0] if matches else None

    def create(self, spec: dict, *, actor: str = "user") -> dict:
        for field in ("name", "purpose", "instructions"):
            if not spec.get(field):
                raise ValueError(f"skill requires field: {field}")
        return self.entities.create("skill", {
            "version": "1.0.0", "status": "active", "author": actor, "builtin": False,
            "input_schema": spec.get("input_schema", {}),
            "output_schema": spec.get("output_schema", {}),
            "tools": spec.get("tools", []), "permissions": spec.get("permissions", ["READ_DATA"]),
            "guardrails": spec.get("guardrails", []), "eval": spec.get("eval", []),
            "domain": spec.get("domain", "custom"),
            "memory_scope": spec.get("memory_scope", []),
            "composed_of": spec.get("composed_of", []),
            "changelog": [{"version": "1.0.0", "at": iso(), "note": "created"}],
            **{k: v for k, v in spec.items() if k not in {"input_schema", "output_schema",
                                                          "tools", "permissions", "guardrails",
                                                          "eval", "domain", "memory_scope",
                                                          "composed_of"}},
        }, actor=actor, idempotency_key=spec.get("idempotency_key"))

    def update(self, skill_id: str, patch: dict, *, actor: str = "user") -> dict:
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(skill_id)
        bump = patch.pop("bump_version", False)
        if bump:
            major, _, rest = str(skill.get("version", "1.0.0")).partition(".")
            minor, _, patch_v = rest.partition(".")
            version = f"{major}.{int(minor or 0) + 1}.0"
            patch["version"] = version
            changelog = list(skill.get("changelog") or [])
            changelog.append({"version": version, "at": iso(),
                              "note": patch.pop("changelog_note", "updated")})
            patch["changelog"] = changelog
        return self.entities.update(skill["id"], patch, actor=actor)

    def duplicate(self, skill_id: str, *, actor: str = "user") -> dict:
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(skill_id)
        clone = {k: v for k, v in skill.items() if k not in
                 {"id", "kind", "created_at", "updated_at", "builtin"}}
        clone["name"] = f"{skill.get('name', 'skill')}-copy"
        clone["author"] = actor
        clone["builtin"] = False
        return self.create(clone, actor=actor)

    def delete(self, skill_id: str, *, actor: str = "user") -> dict:
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(skill_id)
        if skill.get("builtin"):
            raise ValueError("builtin skills can be disabled but not deleted")
        return self.entities.delete(skill["id"], actor=actor)

    def share(self, skill_id: str) -> dict:
        """Export a portable skill definition (no user data)."""
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(skill_id)
        portable = {k: skill.get(k) for k in
                    ("name", "purpose", "instructions", "input_schema", "output_schema",
                     "tools", "permissions", "guardrails", "eval", "domain",
                     "memory_scope", "version", "composed_of")}
        return {"format": "ourex.skill.v1", "skill": portable}

    def test_run(self, skill_id: str, sample_input: dict, *, actor: str = "user") -> dict:
        """Validate schema and permissions without executing side effects."""
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(skill_id)
        if skill.get("status") != "active":
            return {"ok": False, "reason": "skill is disabled"}
        missing = [k for k, t in (skill.get("input_schema") or {}).items()
                   if not str(t).endswith("?") and k not in sample_input]
        steps = [self.get(s).get("name") if self.get(s) else f"missing:{s}"
                 for s in skill.get("composed_of") or []]
        return {"ok": not missing, "missing_inputs": missing,
                "skill": skill.get("name"), "version": skill.get("version"),
                "would_use_tools": skill.get("tools", []),
                "composition_steps": steps,
                "guardrails_checked": skill.get("guardrails", [])}
