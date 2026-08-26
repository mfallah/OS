"""HTTP API surface for the Personal OS — one dispatcher, two hosts.

`dispatch()` is host-neutral: the local dev server (`server.py`) and the
Vercel serverless function (`api/index.py`) both translate their request
objects into this call and return its (status, headers, body) triple.

Conventions:
- JSON only. Errors are {"error": {"code", "message", "setup"?}}.
- Mutations pass through authentication (optional bearer token), rate limiting
  and a 100KB body cap.
- Destructive endpoints require an explicit `confirm=true`.
- Every route is registered in ROUTES; no route logic lives in host code.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from core.app import PersonalOS
from core.entities import ENTITY_KINDS, KIND_FIELD_SUGGESTIONS, KIND_STATUSES, UNIVERSAL_FIELDS, ValidationError
from core.integrations import BaleAdapter, TelegramAdapter, VoicePipeline
from core.security import MAX_BODY_BYTES, RATE_LIMIT_MUTATIONS

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@lru_cache(maxsize=1)
def get_app() -> PersonalOS:
    """One core instance per process (per warm serverless instance)."""
    return PersonalOS()


def _adapters(app: PersonalOS) -> dict:
    if not hasattr(app, "_adapters_cache"):
        app._adapters_cache = {"telegram": TelegramAdapter(app),
                               "bale": BaleAdapter(app),
                               "voice": VoicePipeline(app)}
    return app._adapters_cache


# ------------------------------------------------------------------ routing
class Route:
    def __init__(self, method: str, pattern: str, handler):
        self.method = method
        self.regex = re.compile(f"^{pattern}$")
        self.handler = handler

    def match(self, method: str, path: str):
        if method != self.method:
            return None
        match = self.regex.match(path)
        return match.groupdict() if match else None


ROUTES: list[Route] = []


def route(method: str, pattern: str):
    def wrapper(fn):
        ROUTES.append(Route(method, pattern, fn))
        return fn
    return wrapper


# ------------------------------------------------------------------ helpers
def ok(data, status: int = 200):
    return status, data


def bad_request(message: str, code: str = "bad_request"):
    return 400, {"error": {"code": code, "message": message}}


def not_found(message: str = "not found"):
    return 404, {"error": {"code": "not_found", "message": message}}


def _require_confirm(params: dict):
    if str(params.get("confirm", "")).lower() not in {"true", "1", "yes"}:
        return 409, {"error": {"code": "confirmation_required",
                               "message": "repeat this call with confirm=true to confirm "
                                          "the destructive action"}}
    return None


# ================================================================ endpoints
# ------------------------------------------------------------- system/health
@route("GET", r"/api/health")
def health(app, params, body, headers):
    from core import __version__
    adapters = _adapters(app)
    authenticated_mode = "enforced" if app.auth.enforced else "open"
    import os as _os
    persistence = "explicit PERSONAL_OS_DB" if _os.environ.get("PERSONAL_OS_DB") else \
        ("ephemeral warm-instance (set PERSONAL_OS_DB for durability)"
         if _os.environ.get("VERCEL") else "local sqlite")
    return ok({"status": "operational", "core_version": __version__,
               "persistence": persistence, "auth": authenticated_mode,
               "components": {
                   "event_bus": "online", "graph": "online", "memory": "online",
                   "context_engine": "online", "orchestrator": "online",
                   "workflows": "online", "integrations": {
                       "telegram": adapters["telegram"].status()["mode"],
                       "bale": adapters["bale"].status()["mode"],
                       "voice": "configured" if adapters["voice"].status()["stt_configured"]
                               else "simulated"},
               },
               "counts": {"entities": app.entities.count(),
                          "memories": len(app.memory_store.list(limit=10000)),
                          "pending_approvals": len(app.permissions.pending_approvals())}})


@route("GET", r"/api/state")
def ui_state(app, params, body, headers):
    return ok(app.ui_state())


# ------------------------------------------------------------------ capture
@route("POST", r"/api/capture")
def capture(app, params, body, headers):
    text = (body.get("text") or body.get("title") or "").strip()
    if not text:
        return bad_request("capture requires 'text'")
    result = app.capture_service.capture(
        text, entity=body.get("entity"), actor="user",
        extra={k: v for k, v in body.items() if k not in {"text", "title", "entity"}},
        idempotency_key=body.get("idempotency_key"))
    return ok(result, status=201)


# ----------------------------------------------------------------- entities
@route("GET", r"/api/core/schema")
def schema(app, params, body, headers):
    """Kind catalog + suggested fields + statuses + relations. The UI builds
    its forms from this — suggestions only, never a straightjacket: every
    entity accepts arbitrary extra fields."""
    from core.graph import RELATIONS
    return ok({
        "kinds": ENTITY_KINDS,
        "statuses": KIND_STATUSES,
        "fields": KIND_FIELD_SUGGESTIONS,
        "universal_fields": UNIVERSAL_FIELDS,
        "relations": sorted(RELATIONS),
        "note": "any extra field is stored on any entity — the schema is a starting point",
    })


@route("GET", r"/api/core/entities")
def entities_list(app, params, body, headers):
    kind = params.get("kind")
    if kind and kind not in ENTITY_KINDS:
        return bad_request(f"unknown entity kind: {kind}", "unknown_kind")
    return ok({"items": app.entities.list(kind, limit=int(params.get("limit", 200)),
                                          status=params.get("status"),
                                          tag=params.get("tag"),
                                          q=params.get("q")),
               "kinds": ENTITY_KINDS})


@route("POST", r"/api/core/entities/bulk")
def entities_bulk(app, params, body, headers):
    """Bulk operations: update / tag_add / tag_remove / delete.
    Delete is destructive and requires confirm=true (query or body)."""
    action = body.get("action")
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return bad_request("provide a non-empty 'ids' array")
    if action == "update":
        patch = body.get("patch")
        if not isinstance(patch, dict) or not patch:
            return bad_request("bulk update requires a 'patch' object")
        return ok(app.entities.bulk_update(ids, patch, actor="user"))
    if action in {"tag_add", "tag_remove"}:
        tag = (body.get("tag") or "").strip()
        if not tag:
            return bad_request(f"{action} requires 'tag'")
        return ok(app.entities.bulk_tag(ids, tag, remove=action == "tag_remove",
                                        actor="user"))
    if action == "delete":
        blocked = _require_confirm({**{k: str(v) for k, v in body.items()},
                                    **params})
        if blocked:
            return blocked
        return ok(app.entities.bulk_delete(ids, actor="user"))
    return bad_request("action must be one of update, tag_add, tag_remove, delete",
                       "unknown_action")


@route("GET", r"/api/core/entities/(?P<entity_id>[\w-]+)/history")
def entities_history(app, params, body, headers, entity_id):
    if not app.entities.get(entity_id):
        return not_found(f"entity {entity_id}")
    return ok({"entity_id": entity_id,
               "items": app.entities.history(entity_id,
                                             limit=int(params.get("limit", 50)))})


@route("POST", r"/api/core/entities")
def entities_create(app, params, body, headers):
    kind = body.pop("kind", None)
    if not kind:
        return bad_request("provide a 'kind' field")
    try:
        item = app.entities.create(kind.lower(), body, actor="user",
                                   idempotency_key=body.get("idempotency_key"))
    except ValidationError as exc:
        return bad_request(str(exc), "unknown_kind")
    return ok(item, status=201)


@route("GET", r"/api/core/entities/(?P<entity_id>[\w-]+)")
def entities_get(app, params, body, headers, entity_id):
    item = app.entities.get(entity_id)
    if not item:
        return not_found(f"entity {entity_id}")
    item["graph"] = app.graph.neighbors(entity_id)
    return ok(item)


@route("POST", r"/api/core/entities/(?P<entity_id>[\w-]+)")
def entities_update(app, params, body, headers, entity_id):
    try:
        item = app.entities.update(entity_id, body, actor="user")
    except KeyError:
        return not_found(f"entity {entity_id}")
    return ok(item)


@route("PATCH", r"/api/core/entities/(?P<entity_id>[\w-]+)")
def entities_patch(app, params, body, headers, entity_id):
    return entities_update(app, params, body, headers, entity_id)


@route("DELETE", r"/api/core/entities/(?P<entity_id>[\w-]+)")
def entities_delete(app, params, body, headers, entity_id):
    blocked = _require_confirm(params)
    if blocked:
        return blocked
    try:
        result = app.entities.delete(entity_id, actor="user")
    except KeyError:
        return not_found(f"entity {entity_id}")
    return ok(result)


# legacy alias used by the previous frontend
@route("POST", r"/api/tasks/(?P<entity_id>[\w-]+)")
def tasks_update_alias(app, params, body, headers, entity_id):
    return entities_update(app, params, body, headers, entity_id)


# -------------------------------------------------------------------- graph
@route("GET", r"/api/core/graph")
def graph_view(app, params, body, headers):
    from core.graph import RELATIONS
    if params.get("entity"):
        return ok({"edges": app.graph.neighbors(params["entity"],
                                                relation=params.get("relation")),
                   "relations": sorted(RELATIONS)})
    return ok({"edges": app.graph.edges_for_kind(limit=int(params.get("limit", 300))),
               "relations": sorted(RELATIONS)})


@route("POST", r"/api/core/graph/link")
def graph_link(app, params, body, headers):
    from core.graph import GraphError
    try:
        edge = app.graph.link(body.get("source", ""), body.get("relation", ""),
                              body.get("target", ""), actor="user")
    except GraphError as exc:
        return bad_request(str(exc), "graph_error")
    return ok(edge, status=201)


@route("POST", r"/api/core/graph/unlink")
def graph_unlink(app, params, body, headers):
    return ok(app.graph.unlink(body.get("source", ""), body.get("relation", ""),
                               body.get("target", ""), actor="user"))


# ------------------------------------------------------------------- memory
@route("GET", r"/api/core/memories")
def memories_list(app, params, body, headers):
    return ok({"items": app.memory_store.list(category=params.get("category"),
                                              query=params.get("q"),
                                              limit=int(params.get("limit", 100))),
               "stats": app.memory_store.stats()})


@route("POST", r"/api/core/memory")
def memory_create(app, params, body, headers):
    content = (body.pop("content", None) or "").strip()
    if not content:
        return bad_request("memory requires 'content'")
    category = body.pop("category", "temporary")
    try:
        item = app.memory_store.remember(category, content, **body)
    except ValueError as exc:
        return bad_request(str(exc), "unknown_category")
    return ok(item, status=201)


@route("POST", r"/api/core/memory/(?P<memory_id>[\w-]+)/correct")
def memory_correct(app, params, body, headers, memory_id):
    content = (body.get("content") or "").strip()
    if not content:
        return bad_request("correction requires new 'content'")
    try:
        item = app.memory_store.correct(memory_id, content, actor="user")
    except KeyError:
        return not_found(f"memory {memory_id}")
    return ok(item)


@route("POST", r"/api/core/memory/(?P<memory_id>[\w-]+)/confirm")
def memory_confirm(app, params, body, headers, memory_id):
    try:
        return ok(app.memory_store.confirm(memory_id, actor="user"))
    except KeyError:
        return not_found(f"memory {memory_id}")


@route("DELETE", r"/api/core/memory/(?P<memory_id>[\w-]+)")
def memory_delete(app, params, body, headers, memory_id):
    blocked = _require_confirm(params)
    if blocked:
        return blocked
    try:
        return ok(app.memory_store.delete(memory_id, actor="user"))
    except KeyError:
        return not_found(f"memory {memory_id}")


@route("GET", r"/api/core/memory/export")
def memory_export(app, params, body, headers):
    return ok(app.memory_store.export())


@route("POST", r"/api/core/memory/clear")
def memory_clear(app, params, body, headers):
    blocked = _require_confirm(params)
    if blocked:
        return blocked
    return ok(app.memory_store.clear(actor="user"))


@route("POST", r"/api/core/memory/category/(?P<category>[\w-]+)/(?P<action>disable|enable)")
def memory_category_toggle(app, params, body, headers, category, action):
    try:
        if action == "disable":
            return ok(app.memory_store.disable_category(category))
        return ok(app.memory_store.enable_category(category))
    except ValueError as exc:
        return bad_request(str(exc), "unknown_category")


# ------------------------------------------------------- context / load / ai
@route("GET", r"/api/core/context")
def context_retrieve(app, params, body, headers):
    return ok(app.context.retrieve(params.get("q", ""),
                                   focal_entity=params.get("focal")))


@route("GET", r"/api/core/load")
def cognitive_load(app, params, body, headers):
    return ok(app.state.compute()["cognitive_load"])


@route("GET", r"/api/core/life-debt")
def life_debt(app, params, body, headers):
    return ok(app.state.compute()["life_debt"])


@route("POST", r"/api/core/plan")
def orchestrate(app, params, body, headers):
    message = (body.get("message") or body.get("request") or "").strip()
    if not message:
        return bad_request("provide 'message'")
    result = app.orchestrator.handle(message, focal_entity=body.get("focal_entity"),
                                     actor="user", approved=bool(body.get("approved")))
    status = 200 if result.get("status") == "ok" else 202
    return status, result


@route("GET", r"/api/core/insights")
def insights(app, params, body, headers):
    return ok({"items": app.insights.generate()})


@route("GET", r"/api/core/search")
def search(app, params, body, headers):
    return ok(app.search_engine.search(params.get("q", "")))


@route("GET", r"/api/core/plans/daily")
def daily_plan(app, params, body, headers):
    hours = params.get("hours")
    return ok(app.planner.daily_plan(available_hours=float(hours) if hours else None))


@route("GET", r"/api/core/reviews/weekly")
def weekly_review(app, params, body, headers):
    return ok(app.planner.weekly_review())


@route("GET", r"/api/core/reviews/monthly")
def monthly_review(app, params, body, headers):
    return ok(app.planner.monthly_review())


@route("POST", r"/api/core/research/check-prior")
def research_prior(app, params, body, headers):
    """Before starting research: prior threads, stale data, open questions."""
    topic = body.get("topic", "")
    research = app.entities.list("research", limit=50)
    questions = [q for q in app.entities.list("question", limit=100)
                 if q.get("status") not in {"done", "answered"}]
    related = app.search_engine.search(f"kind:research {topic}")["results"][:5]
    import datetime as _dt
    stale_threshold = (_dt.datetime.now(_dt.timezone.utc) -
                       _dt.timedelta(days=30)).isoformat()
    stale = [r for r in research if r.get("updated_at", "") < stale_threshold]
    return ok({"topic": topic, "prior_research": related,
               "all_open_questions": [{"id": q["id"],
                                       "title": q.get("title") or q.get("question")}
                                      for q in questions][:10],
               "stale_threads": [{"id": r["id"], "title": r.get("title"),
                                  "last_updated": r.get("updated_at"),
                                  "note": "older than 30 days — verify before trusting"}
                                 for r in stale][:5],
               "recommendation": "continue from an existing thread when there is overlap"})


# ------------------------------------------------------------------- agents
@route("GET", r"/api/core/agents")
def agents_list(app, params, body, headers):
    return ok({"items": app.agents.list()})


@route("POST", r"/api/core/agents/(?P<agent_id>[\w-]+)/status")
def agent_status(app, params, body, headers, agent_id):
    try:
        return ok(app.agents.set_status(agent_id, body.get("status", ""), actor="user"))
    except KeyError:
        return not_found(f"agent {agent_id}")
    except ValueError as exc:
        return bad_request(str(exc))


# ------------------------------------------------------------------- skills
@route("GET", r"/api/core/skills")
def skills_list(app, params, body, headers):
    return ok({"items": app.skills.list()})


@route("POST", r"/api/core/skills")
def skills_create(app, params, body, headers):
    try:
        return ok(app.skills.create(body, actor="user"), status=201)
    except ValueError as exc:
        return bad_request(str(exc))


@route("POST", r"/api/core/skills/(?P<skill_id>[\w-]+)")
def skills_update(app, params, body, headers, skill_id):
    try:
        return ok(app.skills.update(skill_id, body, actor="user"))
    except KeyError:
        return not_found(f"skill {skill_id}")


@route("POST", r"/api/core/skills/(?P<skill_id>[\w-]+)/duplicate")
def skills_duplicate(app, params, body, headers, skill_id):
    try:
        return ok(app.skills.duplicate(skill_id, actor="user"), status=201)
    except KeyError:
        return not_found(f"skill {skill_id}")


@route("POST", r"/api/core/skills/(?P<skill_id>[\w-]+)/test")
def skills_test(app, params, body, headers, skill_id):
    try:
        return ok(app.skills.test_run(skill_id, body.get("input", {}), actor="user"))
    except KeyError:
        return not_found(f"skill {skill_id}")


@route("DELETE", r"/api/core/skills/(?P<skill_id>[\w-]+)")
def skills_delete(app, params, body, headers, skill_id):
    blocked = _require_confirm(params)
    if blocked:
        return blocked
    try:
        return ok(app.skills.delete(skill_id, actor="user"))
    except KeyError:
        return not_found(f"skill {skill_id}")
    except ValueError as exc:
        return bad_request(str(exc), "builtin_protected")


@route("GET", r"/api/core/skills/(?P<skill_id>[\w-]+)/share")
def skills_share(app, params, body, headers, skill_id):
    try:
        return ok(app.skills.share(skill_id))
    except KeyError:
        return not_found(f"skill {skill_id}")


# --------------------------------------------------------------- tools / MCP
@route("GET", r"/api/core/tools")
def tools_list(app, params, body, headers):
    items = []
    for tool_status in app.tools.list():
        tool = app.tools.get(tool_status["tool"])
        items.append({**tool_status,
                      **({"auth": tool.authenticate()} if tool.connected else {})})
    return ok({"items": items, "mcp_servers": list(app.tools.mcp_servers)})


@route("POST", r"/api/core/tools/(?P<name>[\w-]+)/execute")
def tools_execute(app, params, body, headers, name):
    try:
        result = app.tools.execute(name, body.get("operation", "read"),
                                   body.get("params", {}), actor="user",
                                   approved=bool(body.get("approved", False)),
                                   idempotency_key=body.get("idempotency_key"))
    except KeyError:
        return not_found(f"tool {name}")
    if not result.get("ok") and result.get("policy") and not result["policy"]["allowed"]:
        return 403, result
    return ok(result)


@route("POST", r"/api/core/mcp/register")
def mcp_register(app, params, body, headers):
    name = (body.get("name") or "").strip()
    if not name:
        return bad_request("provide MCP server 'name'")
    return ok(app.tools.register_mcp_server(name, body.get("config", {})), status=201)


@route("POST", r"/api/core/mcp/execute")
def mcp_execute(app, params, body, headers):
    try:
        result = app.tools.execute_mcp(body.get("server", ""), body.get("tool", ""),
                                       body.get("params", {}), actor="user",
                                       approved=bool(body.get("approved")),
                                       idempotency_key=body.get("idempotency_key"))
    except KeyError as exc:
        return not_found(str(exc))
    if not result.get("ok"):
        return 403, result
    return ok(result)


# ---------------------------------------------------------------- workflows
@route("GET", r"/api/core/workflows")
def workflows_list(app, params, body, headers):
    return ok({"items": app.workflows.list(), "runs": app.workflows.runs(limit=20)})


@route("POST", r"/api/core/workflows")
def workflows_create(app, params, body, headers):
    try:
        return ok(app.workflows.create(body, actor="user"), status=201)
    except ValueError as exc:
        return bad_request(str(exc))


@route("POST", r"/api/core/workflows/run")
def workflows_run(app, params, body, headers):
    workflow_id = body.get("id") or body.get("workflow_id") or body.get("name")
    if not workflow_id:
        return bad_request("provide workflow 'id' or 'name'")
    try:
        result = app.workflows.run(workflow_id, approved=bool(body.get("approved")),
                                   actor="user", approval_id=body.get("approval_id"),
                                   idempotency_key=body.get("idempotency_key"))
    except KeyError:
        return not_found(f"workflow {workflow_id}")
    status = 202 if result.get("status") == "approval_required" else 200
    return status, result


# ---------------------------------------------------------------- approvals
@route("GET", r"/api/core/approvals")
def approvals_list(app, params, body, headers):
    return ok({"items": app.permissions.pending_approvals()})


@route("POST", r"/api/core/approvals/(?P<approval_id>[\w-]+)/decide")
def approvals_decide(app, params, body, headers, approval_id):
    approve = bool(body.get("approve", body.get("approved", False)))
    try:
        decided = app.permissions.decide(approval_id, approve, actor="user")
    except KeyError:
        return not_found(f"approval {approval_id}")
    except ValueError as exc:
        return bad_request(str(exc))
    rerun = None
    if approve:
        payload = decided.get("payload") or {}
        if payload.get("workflow_id") or payload.get("name"):
            ref = payload.get("workflow_id") or payload.get("name")
            try:
                rerun = app.workflows.run(ref, approved=True, actor="user",
                                          approval_id=decided["id"])
            except KeyError:
                rerun = None
    return ok({"approval": decided, "execution": rerun})


# ------------------------------------------------------------ audit / events
@route("GET", r"/api/core/audit")
def audit_log(app, params, body, headers):
    return ok({"items": app.permissions.audit_log(limit=int(params.get("limit", 100)))})


@route("GET", r"/api/core/events")
def events_list(app, params, body, headers):
    return ok({"items": app.events.list(type_=params.get("type"),
                                        limit=int(params.get("limit", 100)))})


# ------------------------------------------------------------- notifications
@route("GET", r"/api/notifications")
def notifications_list(app, params, body, headers):
    return ok(app.notifications.deliverable())


@route("GET", r"/api/notifications/policy")
def notifications_policy(app, params, body, headers):
    return ok(app.notifications.prefs())


@route("POST", r"/api/notifications/policy")
def notifications_policy_set(app, params, body, headers):
    allowed = {"daily_budget", "quiet_hours", "urgency_threshold", "digest_mode", "channel"}
    return ok(app.notifications.set_prefs({k: v for k, v in body.items() if k in allowed}))


@route("POST", r"/api/notifications/(?P<notification_id>[\w-]+)/(?P<action>read|archive|snooze)")
def notifications_action(app, params, body, headers, notification_id, action):
    if action in {"read", "archive"}:
        status = "read" if action == "read" else "archived"
        item = app.notifications.mark(notification_id, status)
    else:
        item = app.notifications.snooze(notification_id,
                                        body.get("until", ""))
    if not item:
        return not_found(f"notification {notification_id}")
    return ok(item)


# ------------------------------------------------------------- integrations
@route("GET", r"/api/integrations/status")
def integrations_status(app, params, body, headers):
    adapters = _adapters(app)
    return ok({"telegram": adapters["telegram"].status(),
               "bale": adapters["bale"].status(),
               "voice": adapters["voice"].status(),
               "tools": app.tools.list()})


@route("POST", r"/api/integrations/telegram/webhook")
def telegram_webhook(app, params, body, headers):
    adapter = _adapters(app)["telegram"]
    if not adapter.verify_webhook(headers):
        return 401, {"error": {"code": "webhook_verification_failed",
                               "message": "set TELEGRAM_WEBHOOK_SECRET and send the "
                                          "secret token header to enable webhooks"}}
    return ok(adapter.handle_update(body))


@route("POST", r"/api/integrations/bale/webhook")
def bale_webhook(app, params, body, headers):
    adapter = _adapters(app)["bale"]
    if not adapter.verify_webhook(headers):
        return 401, {"error": {"code": "webhook_verification_failed",
                               "message": "set BALE_WEBHOOK_SECRET and send the secret "
                                          "token header to enable webhooks"}}
    return ok(adapter.handle_update(body))


@route("POST", r"/api/voice")
def voice_pipeline(app, params, body, headers):
    adapter = _adapters(app)["voice"]
    result = adapter.handle(audio_base64=body.get("audio_base64"),
                            text=body.get("text"), actor="user")
    return (400 if not result.get("ok") else 200), result


# ------------------------------------------------- email/calendar intelligence
@route("POST", r"/api/email/analyze")
def email_analyze(app, params, body, headers):
    return ok(app.capture_service.analyze_message(body.get("body", ""),
                                                  subject=body.get("subject", "")))


@route("POST", r"/api/calendar/analyze")
def calendar_analyze(app, params, body, headers):
    events = body.get("events")
    if not isinstance(events, list):
        return bad_request("provide 'events' as a list")
    return ok(app.capture_service.analyze_calendar(events))


# ----------------------------------------------------------- data ownership
@route("GET", r"/api/export")
def export_all(app, params, body, headers):
    return ok(app.ownership.export_all())


@route("POST", r"/api/restore")
def restore(app, params, body, headers):
    try:
        return ok(app.ownership.restore(body.get("export", body), actor="user"))
    except ValueError as exc:
        return bad_request(str(exc), "invalid_export")


@route("POST", r"/api/data/delete-all")
def delete_all(app, params, body, headers):
    blocked = _require_confirm({**params, **{k: str(v) for k, v in body.items()}})
    if blocked:
        return blocked
    return ok(app.ownership.delete_everything(actor="user"))


# ================================================================ dispatcher
SECURITY_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Idempotency-Key",
    "Cache-Control": "no-store",
}


def dispatch(method: str, path: str, *, query: dict | None = None,
             headers: dict | None = None, body_bytes: bytes = b"",
             client: str = "unknown") -> tuple[int, dict, bytes]:
    """Host-neutral request pipeline. Returns (status, headers, body_bytes)."""
    headers = headers or {}
    query = query or {}
    app = get_app()

    if method == "OPTIONS":
        return 204, SECURITY_HEADERS, b""

    try:
        matched, handler_kwargs = None, {}
        for candidate in ROUTES:
            kwargs = candidate.match(method, path)
            if kwargs is not None:
                matched, handler_kwargs = candidate, kwargs
                break
        if not matched:
            return 404, SECURITY_HEADERS, json.dumps(
                {"error": {"code": "not_found", "message": f"no route {method} {path}"}}
            ).encode()

        if method in MUTATING:
            if len(body_bytes) > MAX_BODY_BYTES:
                return 413, SECURITY_HEADERS, json.dumps(
                    {"error": {"code": "payload_too_large",
                               "message": f"body exceeds {MAX_BODY_BYTES} bytes"}}).encode()
            auth = app.auth.check(headers)
            if not auth["ok"]:
                return 401, SECURITY_HEADERS, json.dumps(
                    {"error": {"code": "unauthorized", "message": auth["error"]}}).encode()
            rate = app.rate_limiter.allow(client, limit=RATE_LIMIT_MUTATIONS)
            if not rate["allowed"]:
                return 429, SECURITY_HEADERS, json.dumps(
                    {"error": {"code": "rate_limited",
                               "message": "too many mutations; slow down",
                               "retry_after": rate["retry_after"]}}).encode()

        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode("utf-8"))
                if not isinstance(body, dict):
                    return 400, SECURITY_HEADERS, json.dumps(
                        {"error": {"code": "invalid_json",
                                   "message": "body must be a JSON object"}}).encode()
            except (UnicodeDecodeError, json.JSONDecodeError):
                return 400, SECURITY_HEADERS, json.dumps(
                    {"error": {"code": "invalid_json",
                               "message": "body is not valid JSON"}}).encode()

        status, payload = matched.handler(app, query, body, headers, **handler_kwargs)
        return status, SECURITY_HEADERS, json.dumps(
            payload, ensure_ascii=False, default=str).encode()

    except (ValidationError, ValueError) as exc:
        return 400, SECURITY_HEADERS, json.dumps(
            {"error": {"code": "validation_error", "message": str(exc)}}).encode()
    except KeyError as exc:
        return 404, SECURITY_HEADERS, json.dumps(
            {"error": {"code": "not_found", "message": str(exc)}}).encode()
    except Exception as exc:  # never leak internals; do return a typed error
        app.events.emit("api.error", {"path": path, "method": method,
                                      "error": type(exc).__name__})
        return 500, SECURITY_HEADERS, json.dumps(
            {"error": {"code": "internal_error",
                       "message": "unexpected server error; the event has been logged"}}).encode()
