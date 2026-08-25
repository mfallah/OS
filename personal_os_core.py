"""Dependency-free Personal OS domain core.

The browser and integrations call this module through an adapter.  It deliberately
contains no Telegram, web framework or model-provider code: interfaces are replaceable.
"""
from __future__ import annotations
import hashlib, json, sqlite3, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

UTC = timezone.utc
RISK = {"informational": 0, "internal": 1, "external": 2, "sensitive": 3}
PERMISSIONS = {"READ_DATA", "WRITE_DATA", "SEND_MESSAGE", "WRITE_CALENDAR", "EXECUTE_FINANCE", "DELETE_DATA"}

def iso(): return datetime.now(UTC).isoformat()
def uid(prefix="ent"): return f"{prefix}_{uuid.uuid4().hex[:12]}"

@dataclass(frozen=True)
class ActionPolicy:
    risk: int
    permission: str
    approval_required: bool
    reason: str

class PersonalOS:
    """Single source of truth for entities, graph edges, memories and audit events."""
    def __init__(self, path: str | Path = "personal_os.sqlite3"):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._migrate()
        self._seed()

    def _migrate(self):
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS entity_kind ON entities(kind);
        CREATE TABLE IF NOT EXISTS edges(source TEXT NOT NULL, relation TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(source, relation, target));
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL, confidence REAL NOT NULL, source TEXT NOT NULL, scope TEXT NOT NULL, importance INTEGER NOT NULL, expires_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, type TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, idempotency_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, actor TEXT NOT NULL, agent TEXT, skill TEXT, tool TEXT, action TEXT NOT NULL, permission TEXT NOT NULL, approved INTEGER NOT NULL, result TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        '''); self.db.commit()

    def _seed(self):
        if self.count("constitution")==0:
            self.create("constitution", {"values":["Clarity","Craft","Relationships"],"principles":["Protect attention","Choose meaningful progress"],"non_negotiables":["Protect deep work","Leave room for recovery"],"risk_tolerance":"moderate","active_project_limit":3})
        if self.count("goal")==0:
            self.create("goal", {"title":"Build a calm, intelligent Personal OS","horizon":"year","status":"active","priority":10})

    def count(self, kind=None):
        q="SELECT COUNT(*) n FROM entities" + (" WHERE kind=?" if kind else "")
        return self.db.execute(q, (kind,) if kind else ()).fetchone()[0]
    def create(self, kind: str, data: dict[str, Any], *, actor="user", idempotency_key=None):
        entity_id=data.pop("id", None) or uid(kind)
        t=iso(); payload={**data,"id":entity_id}
        self.db.execute("INSERT OR REPLACE INTO entities VALUES(?,?,?,?,?)",(entity_id,kind,json.dumps(payload),t,t))
        self.event(f"{kind}.created", {"entity_id":entity_id,"data":payload}, actor=actor, idempotency_key=idempotency_key)
        self.db.commit(); return payload
    def update(self, entity_id: str, patch: dict[str,Any], *, actor="user"):
        row=self.db.execute("SELECT kind,data FROM entities WHERE id=?",(entity_id,)).fetchone()
        if not row: raise KeyError(entity_id)
        data=json.loads(row[1]); data.update(patch); data["id"]=entity_id
        self.db.execute("UPDATE entities SET data=?,updated_at=? WHERE id=?",(json.dumps(data),iso(),entity_id)); self.event(f"{row[0]}.updated",{"entity_id":entity_id,"patch":patch},actor=actor); self.db.commit(); return data
    def list(self, kind=None, limit=200):
        q="SELECT kind,data FROM entities" + (" WHERE kind=?" if kind else "") + " ORDER BY updated_at DESC LIMIT ?"
        return [{"kind":r[0], **json.loads(r[1])} for r in self.db.execute(q, ((kind,) if kind else ())+(limit,))]
    def get(self, entity_id):
        r=self.db.execute("SELECT kind,data FROM entities WHERE id=?",(entity_id,)).fetchone()
        return ({"kind":r[0], **json.loads(r[1])} if r else None)
    def link(self, source, relation, target):
        self.db.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?,?)",(source,relation,target,iso())); self.db.commit()
    def neighbors(self, entity_id, relation=None):
        q="SELECT source,relation,target FROM edges WHERE source=? OR target=?"; args=[entity_id,entity_id]
        if relation: q+=" AND relation=?"; args.append(relation)
        return [dict(r) for r in self.db.execute(q,args)]
    def remember(self, category, content, *, confidence=.5, source="user", scope="personal", importance=5, expires_at=None):
        mid=uid("mem"); now=iso(); self.db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?)",(mid,category,content,float(confidence),source,scope,int(importance),expires_at,now,now)); self.db.commit(); return self.memory(mid)
    def memory(self, mid):
        r=self.db.execute("SELECT * FROM memories WHERE id=?",(mid,)).fetchone(); return dict(r) if r else None
    def memories(self, category=None, query=None, limit=30):
        q="SELECT * FROM memories WHERE (expires_at IS NULL OR expires_at>?)"; args=[iso()]
        if category: q+=" AND category=?"; args.append(category)
        if query: q+=" AND content LIKE ?"; args.append(f"%{query}%")
        q+=" ORDER BY importance DESC, updated_at DESC LIMIT ?"; args.append(limit)
        return [dict(x) for x in self.db.execute(q,args)]
    def event(self, typ, payload, *, actor="system", idempotency_key=None):
        if idempotency_key and self.db.execute("SELECT id FROM events WHERE idempotency_key=?",(idempotency_key,)).fetchone(): return
        self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",(uid("evt"),typ,actor,json.dumps(payload),iso(),idempotency_key))
    def audit(self, action, policy: ActionPolicy, *, actor="system", agent=None, skill=None, tool=None, approved=False, result=None):
        self.db.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?,?)",(uid("audit"),actor,agent,skill,tool,action,policy.permission,int(approved),json.dumps(result or {}),iso())); self.db.commit()
    def authorize(self, action, *, level="informational", approved=False, permissions=None):
        risk=RISK[level]; permission={0:"READ_DATA",1:"WRITE_DATA",2:"SEND_MESSAGE",3:"EXECUTE_FINANCE"}[risk]
        allowed=permissions or {"READ_DATA","WRITE_DATA"}; needs=risk>=2
        policy=ActionPolicy(risk,permission,needs,f"Risk level {risk}; permission {permission}")
        if permission not in allowed or (needs and not approved): return False,policy
        return True,policy
    def context(self, query="", *, kinds=None, limit=20):
        terms=[x.lower() for x in query.split() if len(x)>2]; rows=self.list(limit=500)
        def score(x):
            text=json.dumps(x).lower(); return sum(text.count(t) for t in terms) if terms else 0
        rows=sorted(rows,key=score,reverse=True); rows=[x for x in rows if not kinds or x["kind"] in kinds]
        return {"query":query,"constitution":self.list("constitution",1),"memories":self.memories(query=query,limit=limit),"entities":rows[:limit],"retrieval":"relevance + recency + importance"}
    def cognitive_load(self):
        tasks=self.list("task",500); projects=self.list("project",500); decisions=self.list("decision",500)
        open_tasks=sum(1 for x in tasks if x.get("status") not in {"done","completed","archived"}); overdue=sum(1 for x in tasks if x.get("due") in {"Yesterday","Overdue"})
        score=min(100, open_tasks*4+len(projects)*8+len(decisions)*5+overdue*10)
        return {"score":score,"open_loops":open_tasks,"active_projects":len(projects),"unresolved_decisions":len(decisions),"overdue":overdue,"explanation":"open loops + active projects + unresolved decisions + overdue work"}
    def search(self, query, limit=30): return self.context(query,limit=limit)["entities"]
    def close(self): self.db.close()

class ContextEngine:
    def __init__(self, os): self.os=os
    def retrieve(self, query, domain=None): return self.os.context(query,kinds=domain)
class PermissionEngine:
    def __init__(self, os): self.os=os
    def check(self, level, approved=False, permissions=None): return self.os.authorize("action",level=level,approved=approved,permissions=permissions)
class Orchestrator:
    """Provider-neutral orchestration boundary; model providers plug in at decide()."""
    def __init__(self, os): self.os=os; self.context=ContextEngine(os); self.permissions=PermissionEngine(os)
    def plan(self, request):
        ctx=self.context.retrieve(request); return {"intent":"capture_or_answer","request":request,"context":ctx,"risk":"informational","next":"provider decision required","verification":["validate schema","check permissions","audit action"]}
class WorkflowEngine:
    def __init__(self, os): self.os=os
    def run(self, workflow, *, approved=False):
        ok,policy=self.os.authorize(workflow.get("action","workflow"),level=workflow.get("risk","informational"),approved=approved)
        self.os.audit(workflow.get("name","workflow"),policy,approved=approved,result={"allowed":ok})
        return {"allowed":ok,"policy":policy.__dict__,"status":"executed" if ok else "approval_required"}
