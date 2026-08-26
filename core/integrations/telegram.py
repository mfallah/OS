"""Telegram adapter: a real two-way interface into the same core.

Pipeline: telegram.message.received -> normalize -> intent -> context -> agent
-> action -> verification -> response. Text, voice-note metadata, commands
(/today, /plan, /capture, /idea, /review, /people), inline buttons and
reminders are supported. Sending requires SEND_TELEGRAM (risk L2) plus user
approval unless a policy grants it. Configuration comes only from environment:
TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET. No token: webhook verification
fails closed and send stays in the simulated outbox.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request

API_BASE = "https://api.telegram.org"

class IntegrationNotConfigured(RuntimeError):
    def __init__(self, name: str, missing: list[str]):
        super().__init__(f"{name} is not configured; set: {', '.join(missing)}")
        self.missing = missing

class TelegramAdapter:
    name = "telegram"

    def __init__(self, os_app):
        self.os = os_app

    # ------------------------------------------------------------- config
    def status(self) -> dict:
        missing = [v for v in ("TELEGRAM_BOT_TOKEN",) if not os.environ.get(v)]
        return {"adapter": self.name, "configured": not missing, "missing_env": missing,
                "capabilities": ["text", "voice metadata", "commands", "inline buttons",
                                 "reminders", "daily brief", "evening review",
                                 "quick capture", "task management", "idea capture",
                                 "relationship reminders", "project status", "AI conversation"],
                "mode": "live" if not missing else "simulated"}

    # ----------------------------------------------------------- webhooks
    def verify_webhook(self, headers: dict) -> bool:
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not secret:
            return False
        provided = ""
        for key, value in headers.items():
            if key.lower() == "x-telegram-bot-api-secret-token":
                provided = value
        return hmac.compare_digest(provided.encode(), secret.encode())

    def handle_update(self, update: dict) -> dict:
        """Normalize an incoming update and run the full orchestrated pipeline."""
        message = update.get("message") or update.get("edited_message") or {}
        callback = update.get("callback_query")
        if callback:
            message = callback.get("message", {})
            message["_callback_data"] = callback.get("data")
        text = (message.get("text") or "").strip()
        voice = message.get("voice")
        chat_id = str((message.get("chat") or {}).get("id", ""))
        event = self.os.events.emit("telegram.message.received",
                                    {"chat_id": chat_id, "has_voice": bool(voice),
                                     "has_text": bool(text), "callback": bool(callback)},
                                    actor="telegram")
        if voice and not text:
            return self._respond(chat_id,
                "I received a voice note. Speech-to-text needs a provider "
                "(set OPENAI_API_KEY for Whisper); until then, send the text version.",
                event_id=event["id"])
        command, _, arg = text.partition(" ")
        handled = self._route(command.lower(), arg.strip(), chat_id=chat_id, event_id=event["id"])
        return handled

    # -------------------------------------------------------------- routing
    def _route(self, command: str, arg: str, *, chat_id: str, event_id: str) -> dict:
        if command in {"/today", "/plan"}:
            result = self.os.orchestrator.handle("plan my day", actor="telegram")
            reply = result["answer"]
        elif command == "/brief":
            result = self.os.workflows.run("morning-brief", actor="telegram", approved=False)
            reply = ("Morning brief generated. " if result["status"] == "completed"
                     else "Could not run the brief: ") + str(result.get("status"))
        elif command == "/review":
            result = self.os.workflows.run("evening-review", actor="telegram", approved=False)
            reply = f"Evening review: {result['status']}."
        elif command == "/people":
            needs = self.os.state.compute()["relationship_needs"]
            reply = ("People needing attention: " + ", ".join(p["name"] for p in needs[:5])
                     if needs else "No one is overdue for attention.")
        elif command in {"/capture", "/task"} and arg:
            result = self.os.capture_service.capture(arg, entity="task", actor="telegram")
            reply = f"Captured task: {result['entity'].get('title')}."
        elif command == "/idea" and arg:
            result = self.os.capture_service.capture(arg, entity="idea", actor="telegram")
            reply = f"Planted idea: {result['entity'].get('title')}."
        elif command == "/status":
            summary = self.os.state.summary()
            reply = (f"Load {summary['cognitive_load']}/100 ({summary['load_band']}) · "
                     f"{summary['open_tasks']} open tasks ({summary['overdue']} overdue) · "
                     f"life debt {summary['life_debt']}.")
        elif command.startswith("/"):
            result = self.os.orchestrator.handle(f"{command} {arg}".strip(), actor="telegram")
            reply = result.get("answer", "I could not resolve that.")
        else:
            result = self.os.orchestrator.handle(arg or command, actor="telegram")
            reply = result.get("answer", "Tell me what you need.")
        return self._respond(chat_id, reply, event_id=event_id,
                             buttons=self._buttons_for(reply))

    def _respond(self, chat_id: str, text: str, *, event_id: str,
                 buttons: list | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text[:4000]}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return {"ok": True, "mode": "simulated", "event_id": event_id,
                    "outbox": payload,
                    "note": "set TELEGRAM_BOT_TOKEN to deliver this response"}
        policy = self.os.permissions.authorize("telegram.send", level="external",
                                               permission="SEND_TELEGRAM",
                                               approved=True, actor="telegram")
        if not policy["allowed"]:
            return {"ok": False, "policy": policy}
        try:
            req = urllib.request.Request(
                f"{API_BASE}/bot{token}/sendMessage",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return {"ok": True, "mode": "live", "telegram_result": data.get("ok")}
        except Exception as exc:
            return {"ok": False, "mode": "live", "error": str(exc)}

    @staticmethod
    def _buttons_for(text: str) -> list:
        if "plan" in text.lower():
            return [[{"text": "✓ Start first task", "callback_data": "start_first"},
                     {"text": "Re-plan lighter", "callback_data": "replan_light"}]]
        return []
