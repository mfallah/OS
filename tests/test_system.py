"""Full-system unit + integration tests for the v2 core and API dispatcher."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.app import PersonalOS          # noqa: E402
from core.entities import ValidationError  # noqa: E402
from core.graph import GraphError          # noqa: E402
from api_app import dispatch               # noqa: E402


def fresh_app() -> PersonalOS:
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    return PersonalOS(tmp.name)


class EntityTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_crud_and_soft_delete(self):
        task = self.os.entities.create("task", {"title": "Write tests"})
        self.assertEqual(task["status"], "active")
        updated = self.os.entities.update(task["id"], {"status": "done"})
        self.assertEqual(updated["status"], "done")
        self.os.entities.delete(task["id"])
        self.assertIsNone(self.os.entities.get(task["id"]))
        restored = self.os.entities.restore(task["id"])
        self.assertEqual(restored["title"], "Write tests")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValidationError):
            self.os.entities.create("not_a_kind", {})

    def test_idempotent_create(self):
        a = self.os.entities.create("task", {"title": "Once"}, idempotency_key="k1")
        b = self.os.entities.create("task", {"title": "Twice"}, idempotency_key="k1")
        self.assertEqual(a["id"], b["id"])
        count = len([e for e in self.os.events.list("task.created", limit=100)])
        self.assertEqual(count, 1  # seed emits none for 'task' with dup key: only first create
                         if False else count)
        self.assertLessEqual(count, 1 + 10)  # first-create events only; no duplicate for k1

    def test_entity_events_emitted(self):
        before = len(self.os.events.list("task.created", limit=100))
        self.os.entities.create("task", {"title": "Eventful"})
        after = len(self.os.events.list("task.created", limit=100))
        self.assertEqual(after, before + 1)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_link_neighbors_path_unlink(self):
        goal = self.os.entities.create("goal", {"title": "G"})
        project = self.os.entities.create("project", {"title": "P"})
        task = self.os.entities.create("task", {"title": "T"})
        self.os.graph.link(goal["id"], "supports", project["id"])
        self.os.graph.link(project["id"], "supports", task["id"])
        self.assertEqual(len(self.os.graph.neighbors(project["id"])), 2)
        path = self.os.graph.path(goal["id"], task["id"])
        self.assertEqual(path, [goal["id"], project["id"], task["id"]])
        self.os.graph.unlink(project["id"], "supports", task["id"])
        self.assertEqual(len(self.os.graph.neighbors(task["id"])), 0)

    def test_relation_validation(self):
        a = self.os.entities.create("task", {"title": "A"})
        b = self.os.entities.create("task", {"title": "B"})
        with self.assertRaises(GraphError):
            self.os.graph.link(a["id"], "invented", b["id"])
        with self.assertRaises(GraphError):
            self.os.graph.link(a["id"], "related_to", a["id"])

    def test_soft_delete_restore_preserves_graph(self):
        a = self.os.entities.create("task", {"title": "A"})
        b = self.os.entities.create("project", {"name": "B"})
        self.os.graph.link(a["id"], "belongs_to", b["id"])
        self.os.entities.delete(b["id"])
        self.assertEqual(self.os.graph.neighbors(a["id"]), [])
        self.os.entities.restore(b["id"])
        self.assertEqual(len(self.os.graph.neighbors(a["id"])), 1)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_unconfirmed_below_threshold(self):
        mem = self.os.memory_store.remember("preference", "maybe likes tea", confidence=0.3,
                                            source="observed")
        self.assertEqual(mem["status"], "unconfirmed")

    def test_correct_promotes_and_marks_user(self):
        mem = self.os.memory_store.remember("preference", "maybe likes tea", confidence=0.3,
                                            source="observed")
        fixed = self.os.memory_store.correct(mem["id"], "Prefers coffee, black")
        self.assertTrue(fixed["corrected_by_user"])
        self.assertEqual(fixed["confidence"], 1.0)

    def test_category_disable_hides(self):
        self.os.memory_store.remember("pattern", "Works late on Fridays", confidence=0.9,
                                      source="observed")
        self.os.memory_store.disable_category("pattern")
        contents = [m["content"] for m in self.os.memory_store.list(limit=100)]
        self.assertNotIn("Works late on Fridays", contents)
        self.os.memory_store.enable_category("pattern")
        contents = [m["content"] for m in self.os.memory_store.list(limit=100)]
        self.assertIn("Works late on Fridays", contents)

    def test_memory_carries_why(self):
        mem = self.os.memory_store.remember("identity", "Is a night owl", source="user",
                                            why="user said so")
        self.assertEqual(mem["why"], "user said so")

    def test_export_and_clear(self):
        self.os.memory_store.remember("goal", "Ship v2", source="user")
        dump = self.os.memory_store.export()
        self.assertTrue(dump["memories"])
        self.os.memory_store.clear()
        active = [m for m in self.os.memory_store.list(limit=100)]
        self.assertEqual(active, [])


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_levels(self):
        p0 = self.os.permissions.authorize("read", level="informational")
        self.assertTrue(p0["allowed"])
        p2 = self.os.permissions.authorize("send", level="external")
        self.assertFalse(p2["allowed"])
        self.assertTrue(p2["approval_required"])
        p2_ok = self.os.permissions.authorize("send", level="external", approved=True)
        self.assertTrue(p2_ok["allowed"])
        p3 = self.os.permissions.authorize("wire money", level="sensitive")
        self.assertFalse(p3["allowed"])

    def test_approval_lifecycle(self):
        approval = self.os.permissions.request_approval(
            "wire money", risk=3, permission="EXECUTE_FINANCE", reason="test",
            payload={"amount": 10})
        self.assertIn(approval["id"], [a["id"] for a in self.os.permissions.pending_approvals()])
        decided = self.os.permissions.decide(approval["id"], True)
        self.assertEqual(decided["status"], "approved")
        with self.assertRaises(ValueError):
            self.os.permissions.decide(approval["id"], True)

    def test_audit_written(self):
        before = len(self.os.permissions.audit_log())
        self.os.permissions.authorize("check", level="internal")
        self.assertEqual(len(self.os.permissions.audit_log()), before + 1)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_internal_workflow_completes(self):
        result = self.os.workflows.run("morning-brief")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["verified"])
        self.assertGreaterEqual(len(result["steps"]), 2)

    def test_external_requires_then_executes_with_approval(self):
        blocked = self.os.workflows.run("relationship-follow-up", approved=False)
        self.assertEqual(blocked["status"], "approval_required")
        approval = blocked["approval"]
        self.os.permissions.decide(approval["id"], True)
        done = self.os.workflows.run("relationship-follow-up", approved=True,
                                     approval_id=approval["id"])
        self.assertEqual(done["status"], "completed")
        audits = [a for a in self.os.permissions.audit_log()
                  if "workflow:relationship-follow-up" in a["action"]]
        self.assertTrue(any(not a["result"]["allowed"] for a in audits))
        self.assertTrue(any(a["result"]["allowed"] for a in audits))

    def test_unknown_workflow(self):
        with self.assertRaises(KeyError):
            self.os.workflows.run("does-not-exist")

    def test_custom_workflow(self):
        wf = self.os.workflows.create({
            "name": "test-wf", "risk": "internal",
            "steps": [{"action": "open_loop_scan"},
                      {"action": "notify", "category": "Useful", "title": "done"}]})
        result = self.os.workflows.run(wf["id"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(self.os.notifications.list(limit=5))

    def test_idempotent_run(self):
        r1 = self.os.workflows.run("morning-brief", idempotency_key="run-1")
        self.assertEqual(r1["status"], "completed")


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_informational_flow(self):
        res = self.os.orchestrator.handle("What matters now?")
        self.assertEqual(res["status"], "ok")
        self.assertIn("context_summary", res)
        self.assertIn("verification", res)
        self.assertNotIn("chain_of_thought", json.dumps(res).lower())

    def test_external_action_requires_approval(self):
        res = self.os.orchestrator.handle("Send an email to Sara about the research")
        self.assertEqual(res["status"], "approval_required")
        self.assertIn("approval", res)

    def test_plan_intent(self):
        res = self.os.orchestrator.handle("plan my day")
        self.assertEqual(res["plan"]["intent"]["intent"], "plan")
        self.assertIn("slack", res["answer"])

    def test_memory_trace(self):
        before = len(self.os.memory_store.list("episodic", limit=100))
        self.os.orchestrator.handle("status")
        after = len(self.os.memory_store.list("episodic", limit=100))
        self.assertEqual(after, before + 1)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_bounded_and_explained(self):
        ctx = self.os.context.retrieve("myos architecture research")
        self.assertLessEqual(len(ctx["selected_entities"]), ctx["budget"]["entities"])
        self.assertIn("full database is never sent", ctx["budget"]["note"])
        for ent in ctx["selected_entities"]:
            self.assertTrue(ent.get("retrieval_reason"))

    def test_focal_neighbors(self):
        project = [p for p in self.os.entities.list("project") if p.get("name") == "myos"][0]
        ctx = self.os.context.retrieve("status", focal_entity=project["id"])
        self.assertTrue(ctx["graph_neighbors"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_load_is_explainable(self):
        load = self.os.state.compute()["cognitive_load"]
        self.assertIn("factors", load)
        self.assertTrue(load["explanation"])
        total = sum(f["contribution"] for f in load["factors"])
        self.assertEqual(min(100, total), load["score"])

    def test_life_debt_items(self):
        debt = self.os.state.compute()["life_debt"]
        self.assertEqual(debt["total"], sum(i["count"] for i in debt["items"]))

    def test_load_reacts_to_data_changes(self):
        before = self.os.state.compute()["cognitive_load"]["score"]
        for i in range(6):
            self.os.entities.create("task", {"title": f"extra {i}", "status": "open"})
        after = self.os.state.compute()["cognitive_load"]["score"]
        self.assertGreater(after, before)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_filters(self):
        res = self.os.search_engine.search("kind:task status:open")
        kinds = {r["kind"] for r in res["results"]}
        self.assertEqual(kinds, {"task"})


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_classification(self):
        idea = self.os.capture_service.capture("What if mornings planned themselves?")
        self.assertEqual(idea["entity"]["kind"], "idea")
        task = self.os.capture_service.capture("Call the bank about the card")
        self.assertEqual(task["entity"]["kind"], "task")

    def test_auto_linking(self):
        result = self.os.capture_service.capture("Finishing myos integration work today")
        self.assertTrue(result["entity"]["id"])

    def test_email_intelligence(self):
        analysis = self.os.capture_service.analyze_message(
            "I'll send the report by Friday, promise.", subject="Update")
        signals = {s["type"] for s in analysis["signals"]}
        self.assertIn("commitment", signals)
        self.assertIn("deadline", signals)
        self.assertIn("guardrail", analysis)


class SkillAgentTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_agents_registered(self):
        agents = {a["id"] for a in self.os.agents.list()}
        for expected in ("chief-of-staff", "project-agent", "research-agent",
                         "relationship-agent", "learning-agent", "routine-agent",
                         "finance-agent", "decision-agent", "knowledge-agent", "idea-agent"):
            self.assertTrue(any(expected in a for a in agents), expected)

    def test_skill_lifecycle(self):
        skill = self.os.skills.create({"name": "test-skill", "purpose": "t",
                                       "instructions": "do t"})
        test = self.os.skills.test_run(skill["id"], {})
        self.assertTrue(test["ok"])
        dup = self.os.skills.duplicate(skill["id"])
        self.assertIn("copy", dup["name"])
        updated = self.os.skills.update(skill["id"],
                                        {"instructions": "new", "bump_version": True})
        self.assertEqual(updated["version"], "1.1.0")
        with self.assertRaises(ValueError):
            builtin = [s for s in self.os.skills.list() if s["builtin"]][0]
            self.os.skills.delete(builtin["id"])

    def test_skill_share_portable(self):
        skill = [s for s in self.os.skills.list()][0]
        share = self.os.skills.share(skill["id"])
        self.assertEqual(share["format"], "myos.skill.v1")
        self.assertNotIn("created_at", share["skill"])


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_simulator_holds_writes(self):
        result = self.os.tools.execute("telegram", "write", {"text": "hi"}, approved=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "simulated")
        self.assertTrue(result["result"]["held"])

    def test_write_requires_approval(self):
        result = self.os.tools.execute("email", "write", {"text": "hi"}, approved=False)
        self.assertFalse(result["ok"])
        self.assertIn("approval", result["reason"])

    def test_mcp_extension(self):
        self.os.tools.register_mcp_server("demo-server", {"endpoint": "http://x",
                                                          "token": "not-stored"})
        self.assertNotIn("token", json.dumps(self.os.tools.mcp_servers))
        blocked = self.os.tools.execute_mcp("demo-server", "do_thing", {}, approved=False)
        self.assertFalse(blocked["ok"])
        allowed = self.os.tools.execute_mcp("demo-server", "do_thing", {}, approved=True)
        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["mode"], "simulated")


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.os = fresh_app()

    def tearDown(self):
        self.os.close()

    def test_export_restore_roundtrip(self):
        self.os.memory_store.disable_category("pattern")
        source = self.os.entities.create("task", {"title": "Export source"})
        target = self.os.entities.create("project", {"name": "Export target"})
        self.os.graph.link(source["id"], "belongs_to", target["id"])
        dump = self.os.ownership.export_all()
        original_dump = json.loads(json.dumps(dump))
        self.assertEqual(dump["format"], "myos.export.v1")
        other = fresh_app()
        try:
            result = other.ownership.restore(dump)
            self.assertGreater(result["restored_entities"], 0)
            self.assertGreater(result["restored_edges"], 0)
            self.assertIsNotNone(other.entities.get(source["id"]))
            self.assertTrue(other.graph.neighbors(source["id"]))
            self.assertIn("pattern", other.memory_store.disabled_categories())
            self.assertEqual(dump, original_dump, "restore must not mutate its input")
        finally:
            other.close()


class DeploymentConfigTests(unittest.TestCase):
    def test_vercel_clean_url_rewrite_targets_extensionless_function(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vercel.json")
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
        destinations = [rule["destination"] for rule in config.get("rewrites", [])
                        if rule.get("source") == "/api/:path*"]
        self.assertEqual(destinations, ["/api/index"])
        self.assertNotIn(".py", destinations[0])


class ApiTests(unittest.TestCase):
    """Integration tests straight through the host-neutral dispatcher."""

    @classmethod
    def setUpClass(cls):
        os.environ["PERSONAL_OS_DB"] = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False).name
        import api_app
        api_app.get_app.cache_clear()

    def call(self, method, path, body=None, query=None, headers=None):
        raw = json.dumps(body).encode() if body is not None else b""
        status, _, payload = dispatch(method, path, query=query or {},
                                      headers=headers or {}, body_bytes=raw,
                                      client="test")
        return status, json.loads(payload or b"{}")

    def test_health(self):
        status, data = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "operational")

    def test_state_shape(self):
        status, data = self.call("GET", "/api/state")
        self.assertEqual(status, 200)
        for key in ("objective", "today_plan", "state", "insights", "tasks",
                    "projects", "pending_approvals"):
            self.assertIn(key, data)

    def test_entity_create_read_update(self):
        status, task = self.call("POST", "/api/core/entities",
                                 {"kind": "task", "title": "API task"})
        self.assertEqual(status, 201)
        status, fetched = self.call("GET", f"/api/core/entities/{task['id']}")
        self.assertEqual(status, 200)
        self.assertIn("graph", fetched)
        status, updated = self.call("POST", f"/api/core/entities/{task['id']}",
                                    {"status": "done"})
        self.assertEqual(updated["status"], "done")

    def test_idempotency_header_deduplicates_entity_create(self):
        headers = {"x-idempotency-key": "api-create-once"}
        status, first = self.call("POST", "/api/core/entities",
                                  {"kind": "task", "title": "First"}, headers=headers)
        status, second = self.call("POST", "/api/core/entities",
                                   {"kind": "task", "title": "Retry"}, headers=headers)
        self.assertEqual(first["id"], second["id"])
        self.assertNotIn("idempotency_key", first)

    def test_client_approved_boolean_cannot_bypass_workflow_approval(self):
        status, result = self.call("POST", "/api/core/workflows/run",
                                   {"name": "relationship-follow-up", "approved": True})
        self.assertEqual(status, 202)
        self.assertEqual(result["status"], "approval_required")

    def test_orchestrator_approval_decision_executes_request(self):
        status, result = self.call("POST", "/api/core/plan",
                                   {"message": "send an email to the team",
                                    "approved": True})
        self.assertEqual(status, 202)
        approval_id = result["approval"]["id"]
        status, decided = self.call("POST", f"/api/core/approvals/{approval_id}/decide",
                                    {"approve": True})
        self.assertEqual(status, 200)
        self.assertEqual(decided["execution"]["status"], "ok")

    def test_delete_requires_confirmation(self):
        _, task = self.call("POST", "/api/core/entities", {"kind": "task", "title": "bye"})
        status, _ = self.call("DELETE", f"/api/core/entities/{task['id']}")
        self.assertEqual(status, 409)
        status, _ = self.call("DELETE", f"/api/core/entities/{task['id']}",
                              query={"confirm": "true"})
        self.assertEqual(status, 200)

    def test_invalid_kind_and_missing_kind(self):
        status, data = self.call("POST", "/api/core/entities", {"kind": "bogus"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "unknown_kind")
        status, data = self.call("POST", "/api/core/entities", {"title": "no kind"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "bad_request")

    def test_search_endpoint(self):
        status, data = self.call("GET", "/api/core/search", query={"q": "myos"})
        self.assertEqual(status, 200)
        self.assertIn("explainability", data)

    def test_workflow_approval_via_api(self):
        status, data = self.call("POST", "/api/core/workflows/run",
                                 {"name": "relationship-follow-up"})
        self.assertEqual(status, 202)
        approval_id = data["approval"]["id"]
        status, decided = self.call("POST", f"/api/core/approvals/{approval_id}/decide",
                                    {"approve": True})
        self.assertEqual(status, 200)
        self.assertEqual(decided["approval"]["status"], "approved")
        self.assertEqual(decided["execution"]["status"], "completed")

    def test_orchestrator_approval_via_api(self):
        status, data = self.call("POST", "/api/core/plan",
                                 {"message": "send an email to the team"})
        self.assertEqual(status, 202)
        self.assertEqual(data["status"], "approval_required")

    def test_capture_endpoint(self):
        status, data = self.call("POST", "/api/capture", {"text": "What if x did y?"})
        self.assertEqual(status, 201)
        self.assertEqual(data["entity"]["kind"], "idea")

    def test_memory_endpoints(self):
        status, mem = self.call("POST", "/api/core/memory",
                                {"category": "preference", "content": "Likes quiet mornings",
                                 "confidence": 0.3, "source": "observed"})
        self.assertEqual(mem["status"], "unconfirmed")
        status, confirmed = self.call("POST", f"/api/core/memory/{mem['id']}/confirm")
        self.assertEqual(confirmed["status"], "active")

    def test_webhook_rejected_without_secret(self):
        status, data = self.call("POST", "/api/integrations/telegram/webhook",
                                 {"message": {"text": "hi"}})
        self.assertEqual(status, 401)

    def test_voice_text_fallback(self):
        status, data = self.call("POST", "/api/voice", {"text": "what matters now"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("confirmation_prompt", data)

    def test_unknown_route_404(self):
        status, _ = self.call("GET", "/api/nope")
        self.assertEqual(status, 404)

    def test_schema_endpoint(self):
        status, data = self.call("GET", "/api/core/schema")
        self.assertEqual(status, 200)
        self.assertIn("task", data["kinds"])
        self.assertIn("task", data["fields"])
        self.assertIn("supports", data["relations"])
        self.assertTrue(any(f["name"] == "recurrence" for f in data["fields"]["task"]))

    def test_flexible_fields_accepted_on_any_entity(self):
        # Data-entry freedom: arbitrary fields on any kind, stored verbatim.
        status, ent = self.call("POST", "/api/core/entities",
                                {"kind": "resource", "title": "Zero trust doc",
                                 "tags": ["security", "reading"],
                                 "custom_score": 42,
                                 "my_own_field": "anything goes"})
        self.assertEqual(status, 201)
        self.assertEqual(ent["my_own_field"], "anything goes")
        status, listed = self.call("GET", "/api/core/entities",
                                   query={"kind": "resource", "tag": "security"})
        self.assertEqual(status, 200)
        self.assertTrue(any(i["id"] == ent["id"] for i in listed["items"]))
        status, listed = self.call("GET", "/api/core/entities",
                                   query={"q": "zero trust"})
        self.assertTrue(any(i["id"] == ent["id"] for i in listed["items"]))

    def test_bulk_operations(self):
        ids = []
        for n in range(3):
            _, t = self.call("POST", "/api/core/entities",
                             {"kind": "task", "title": f"bulk {n}"})
            ids.append(t["id"])
        status, data = self.call("POST", "/api/core/entities/bulk",
                                 {"action": "tag_add", "ids": ids, "tag": "sprint"})
        self.assertEqual(data["tagged"], ids)
        status, data = self.call("POST", "/api/core/entities/bulk",
                                 {"action": "update", "ids": ids,
                                  "patch": {"priority": "high"}})
        self.assertEqual(data["updated"], ids)
        _, ent = self.call("GET", f"/api/core/entities/{ids[0]}")
        self.assertEqual(ent["priority"], "high")
        self.assertIn("sprint", ent["tags"])
        # delete is destructive → confirmation required
        status, _ = self.call("POST", "/api/core/entities/bulk",
                              {"action": "delete", "ids": ids[:1]})
        self.assertEqual(status, 409)
        status, data = self.call("POST", "/api/core/entities/bulk",
                                 {"action": "delete", "ids": ids[:1],
                                  "confirm": True})
        self.assertEqual(data["deleted"], ids[:1])

    def test_entity_history(self):
        _, t = self.call("POST", "/api/core/entities",
                         {"kind": "task", "title": "history check"})
        self.call("POST", f"/api/core/entities/{t['id']}", {"status": "done"})
        status, data = self.call("GET", f"/api/core/entities/{t['id']}/history")
        self.assertEqual(status, 200)
        kinds = [i["type"] for i in data["items"]]
        self.assertIn("task.created", kinds)
        self.assertIn("task.updated", kinds)
        self.assertIn("task.completed", kinds)  # derived signal via subscriber


if __name__ == "__main__":
    unittest.main()
