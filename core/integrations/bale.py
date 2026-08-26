"""Bale messenger adapter (bale.ai/Bale Bot API is Telegram-compatible).

Mirrors the Telegram adapter contract through the same pipeline. Configuration:
BALE_BOT_TOKEN, BALE_WEBHOOK_SECRET — read from the environment only.
"""
from __future__ import annotations

import hmac
import json
import os
import urllib.request

from .telegram import TelegramAdapter

API_BASE = "https://tapi.bale.ai"

class BaleAdapter(TelegramAdapter):
    name = "bale"

    def status(self) -> dict:
        missing = [v for v in ("BALE_BOT_TOKEN",) if not os.environ.get(v)]
        base = super().status()
        return {**base, "adapter": self.name, "configured": not missing,
                "missing_env": missing, "mode": "live" if not missing else "simulated"}

    def verify_webhook(self, headers: dict) -> bool:
        secret = os.environ.get("BALE_WEBHOOK_SECRET")
        if not secret:
            return False
        provided = ""
        for key, value in headers.items():
            if key.lower() in {"x-bale-bot-api-secret-token",
                               "x-telegram-bot-api-secret-token"}:
                provided = value
        return hmac.compare_digest(provided.encode(), secret.encode())

    def _respond(self, chat_id: str, text: str, *, event_id: str,
                 buttons: list | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text[:4000]}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        token = os.environ.get("BALE_BOT_TOKEN")
        if not token:
            return {"ok": True, "mode": "simulated", "event_id": event_id,
                    "outbox": payload,
                    "note": "set BALE_BOT_TOKEN to deliver this response"}
        policy = self.os.permissions.authorize("bale.send", level="external",
                                               permission="SEND_BALE",
                                               approved=True, actor="bale")
        if not policy["allowed"]:
            return {"ok": False, "policy": policy}
        try:
            req = urllib.request.Request(
                f"{API_BASE}/bot{token}/sendMessage",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return {"ok": True, "mode": "live", "bale_result": data.get("ok")}
        except Exception as exc:
            return {"ok": False, "mode": "live", "error": str(exc)}
