"""Voice pipeline: audio -> STT -> intent -> context -> entity extraction ->
action -> confirmation.

STT is provider-based (env-configured). Without a provider the adapter returns
a typed `stt_unavailable` result with setup instructions — never a fake
transcript. A text fallback keeps the whole pipeline testable end-to-end.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request

from .telegram import IntegrationNotConfigured

class VoicePipeline:
    name = "voice"

    def __init__(self, os_app):
        self.os = os_app

    def status(self) -> dict:
        configured = bool(os.environ.get("OPENAI_API_KEY") or
                          os.environ.get("STT_PROVIDER"))
        return {"adapter": self.name, "stt_configured": configured,
                "pipeline": ["audio", "speech-to-text", "intent detection",
                             "context resolution", "entity extraction",
                             "action", "confirmation"],
                "missing_env": [] if configured else ["OPENAI_API_KEY (or STT_PROVIDER)"]}

    def transcribe(self, audio_base64: str, *, fmt: str = "wav") -> dict:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise IntegrationNotConfigured("voice STT", ["OPENAI_API_KEY"])
        audio = base64.b64decode(audio_base64)
        boundary = "ourexvoice"
        body = b"\r\n".join([
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="model"',
            b"", b"whisper-1",
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="file"; filename="audio.{fmt}"'.encode(),
            b"Content-Type: application/octet-stream", b"", audio,
            f"--{boundary}--".encode(), b""])
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions", data=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())

    # ----------------------------------------------------------- pipeline
    def handle(self, *, audio_base64: str | None = None, text: str | None = None,
               actor: str = "user") -> dict:
        self.os.events.emit("voice.received", {"has_audio": bool(audio_base64)},
                            actor=actor)
        if audio_base64 and not text:
            try:
                text = self.transcribe(audio_base64).get("text", "")
            except IntegrationNotConfigured as exc:
                return {"ok": False, "stage": "speech-to-text", "error": str(exc),
                        "missing_env": exc.missing,
                        "fallback": "POST the same request with `text` instead of audio"}
        if not text:
            return {"ok": False, "stage": "input", "error": "no audio or text provided"}

        intent = self.os.orchestrator.detect_intent(text)
        extracted = self._extract_entities(text)
        result = self.os.orchestrator.handle(text, actor=actor)
        return {"ok": True, "transcript": text, "intent": intent,
                "entities_extracted": extracted,
                "action_result": {"status": result.get("status"),
                                  "answer": result.get("answer")},
                "confirmation_required": result.get("status") == "approval_required",
                "confirmation_prompt": (
                    f"I understood: {intent['intent']} "
                    f"(confidence {intent['confidence']:.0%}). Confirm to proceed."
                    if result.get("status") == "approval_required"
                    else "Done — no confirmation needed for informational actions.")}

    @staticmethod
    def _extract_entities(text: str) -> list[dict]:
        found = []
        lowered = text.lower()
        for marker, kind in (("with ", "person"), ("about ", "topic"),
                             ("for ", "project"), ("by ", "deadline")):
            if marker in lowered:
                tail = lowered.split(marker, 1)[1].split()
                if tail:
                    found.append({"kind": kind, "mention": " ".join(tail[:3])})
        return found[:4]
