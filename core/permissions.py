"""Permission, risk and approval engine.

Risk levels:
  L0 informational    - read-only answers
  L1 internal low-risk change (create task, update note)
  L2 external action (send message/email, write calendar)
  L3 sensitive or financial operation

L2+ requires an explicit approval unless a stored policy grants autonomy.
Every decision is written to the audit log with actor, agent, skill, tool,
permission, risk and outcome.
"""
from __future__ import annotations

from .util import dumps, iso, uid

RISK = {"informational": 0, "internal": 1, "external": 2, "sensitive": 3}
RISK_NAMES = {v: k for k, v in RISK.items()}

PERMISSIONS = {
    "READ_EMAIL", "SEND_EMAIL", "READ_TELEGRAM", "SEND_TELEGRAM", "READ_BALE",
    "SEND_BALE", "READ_CALENDAR", "WRITE_CALENDAR", "READ_CONTACTS",
    "WRITE_CONTACTS", "READ_FINANCE", "EXECUTE_FINANCE", "READ_FILES",
    "DELETE_FILES", "MANAGE_MEMORY", "MANAGE_WORKFLOWS", "MANAGE_SKILLS",
    "MANAGE_AGENTS", "READ_DATA", "WRITE_DATA",
}

#: Default permission each risk level maps to when a caller does not specify one.
DEFAULT_PERMISSION = {0: "READ_DATA", 1: "WRITE_DATA", 2: "SEND_EMAIL", 3: "EXECUTE_FINANCE"}

class PermissionEngine:
    def __init__(self, db, events):
        self.db = db
        self.events = events

    def authorize(self, action: str, *, level: str | int = "informational",
                  permission: str | None = None, approved: bool = False,
                  actor: str = "system", agent: str | None = None,
                  skill: str | None = None, tool: str | None = None,
                  granted: set | None = None, result: dict | None = None) -> dict:
        risk = RISK[level] if isinstance(level, str) else int(level)
        permission = permission or DEFAULT_PERMISSION.get(risk, "WRITE_DATA")
        if permission not in PERMISSIONS:
            raise ValueError(f"unknown permission: {permission}")
        scope = granted if granted is not None else set(PERMISSIONS)
        needs_approval = risk >= 2
        allowed = permission in scope and (not needs_approval or approved)
        reason = self._reason(risk, permission, needs_approval, approved, permission in scope)
        policy = {"risk": risk, "risk_name": RISK_NAMES[risk], "permission": permission,
                  "approval_required": needs_approval, "approved": bool(approved),
                  "allowed": allowed, "reason": reason}
        self.audit(action, policy, actor=actor, agent=agent, skill=skill, tool=tool,
                   result=result or {})
        return policy

    def _reason(self, risk, permission, needs, approved, in_scope) -> str:
        if not in_scope:
            return f"permission {permission} not granted to this actor"
        if needs and not approved:
            return f"risk level {risk} ({RISK_NAMES[risk]}) requires explicit user approval"
        if needs and approved:
            return f"risk level {risk} approved by user"
        return f"risk level {risk} ({RISK_NAMES[risk]}) allowed without approval"

    # ------------------------------------------------------------- approvals
    def request_approval(self, action: str, *, risk: int, permission: str,
                         reason: str, payload: dict, context: dict | None = None) -> dict:
        approval_id = uid("apr")
        self.db.execute(
            "INSERT INTO approvals(id,action,reason,risk,permission,payload,status,context,created_at)"
            " VALUES(?,?,?,?,?,?,'pending',?,?)",
            (approval_id, action, reason, int(risk), permission, dumps(payload),
             dumps(context or {}), iso()))
        self.events.emit("approval.requested", {"approval_id": approval_id,
                                                "action": action, "risk": risk})
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict | None:
        row = self.db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
        return self._map_approval(row) if row else None

    def pending_approvals(self) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at DESC")
        return [self._map_approval(r) for r in rows]

    def decide(self, approval_id: str, approve: bool, *, actor: str = "user") -> dict:
        approval = self.get_approval(approval_id)
        if not approval:
            raise KeyError(approval_id)
        if approval["status"] != "pending":
            raise ValueError("approval already decided")
        status = "approved" if approve else "denied"
        self.db.execute("UPDATE approvals SET status=?, decided_at=?, actor=? WHERE id=?",
                        (status, iso(), actor, approval_id))
        self.events.emit(f"approval.{status}", {"approval_id": approval_id}, actor=actor)
        return self.get_approval(approval_id)

    # ----------------------------------------------------------------- audit
    def audit(self, action: str, policy: dict, *, actor: str = "system",
              agent: str | None = None, skill: str | None = None,
              tool: str | None = None, result: dict | None = None) -> dict:
        audit_id = uid("aud")
        self.db.execute(
            "INSERT INTO audit(id,actor,agent,skill,tool,action,permission,risk,approved,result,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (audit_id, actor, agent, skill, tool, action, policy["permission"],
             policy["risk"], int(policy.get("approved", False)),
             dumps({**(result or {}), "allowed": policy["allowed"]}), iso()))
        return {"id": audit_id}

    def audit_log(self, limit: int = 100) -> list[dict]:
        rows = self.db.query("SELECT * FROM audit ORDER BY created_at DESC LIMIT ?",
                             (int(limit),))
        from .util import loads
        return [{"id": r["id"], "actor": r["actor"], "agent": r["agent"],
                 "skill": r["skill"], "tool": r["tool"], "action": r["action"],
                 "permission": r["permission"], "risk": r["risk"],
                 "approved": bool(r["approved"]), "result": loads(r["result"] or "{}"),
                 "created_at": r["created_at"]} for r in rows]

    @staticmethod
    def _map_approval(row) -> dict:
        from .util import loads
        return {"id": row["id"], "action": row["action"], "reason": row["reason"],
                "risk": row["risk"], "risk_name": RISK_NAMES.get(row["risk"], "?"),
                "permission": row["permission"], "payload": loads(row["payload"]),
                "status": row["status"], "context": loads(row["context"] or "{}"),
                "created_at": row["created_at"], "decided_at": row["decided_at"],
                "actor": row["actor"]}
