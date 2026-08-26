"""Model provider abstraction.

The orchestrator talks to a provider through one interface. Providers are
selected via environment variables — never hardcoded — and any missing
configuration fails as clean data, not a crash. The built-in demo provider is
deterministic and offline, so the system always works with zero keys.
"""
from __future__ import annotations

import json
import os
import urllib.request

class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, setup: str | None = None):
        super().__init__(message)
        self.provider = provider
        self.setup = setup

class BaseProvider:
    name = "base"
    model = None

    def available(self) -> bool:
        raise NotImplementedError

    def complete(self, prompt_layers: dict, *, max_tokens: int = 800) -> dict:
        """Prompt layers: system_identity, safety_policy, agent_role,
        skill_instructions, constitution, memories, personal_state,
        task_context, output_contract. Never a single giant blob."""
        raise NotImplementedError

class DemoProvider(BaseProvider):
    """Deterministic offline provider: real synthesis, zero network."""
    name = "demo"

    def available(self) -> bool:
        return True

    def complete(self, prompt_layers: dict, *, max_tokens: int = 800) -> dict:
        task = prompt_layers.get("task_context", {})
        state = prompt_layers.get("personal_state", {})
        memories = prompt_layers.get("memories", [])
        constitution = prompt_layers.get("constitution", [])
        bullets = []
        if state:
            bullets.append(f"Current state: {state.get('open_tasks', 0)} open tasks, "
                           f"load {state.get('cognitive_load', '?')}/100 "
                           f"({state.get('load_band', 'unknown')}).")
        for m in memories[:3]:
            bullets.append(f"Remembered ({m.get('category')}): {m.get('content')}")
        for c in constitution[:2]:
            bullets.append(f"Constitution: {c.get('content')}")
        answer = task.get("draft") or (
            "Based on your current context, the highest-leverage move is the top "
            "prioritized item in your plan. " + " ".join(bullets[:2]))
        return {"provider": self.name, "model": "deterministic-demo",
                "text": answer,
                "supporting_context": bullets,
                "explanation": "demo provider synthesizes from retrieved context only"}

class _HTTPJSONProvider(BaseProvider):
    env_key = ""
    endpoint = ""

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key))

    def _post(self, payload: dict, headers: dict, timeout: int = 30) -> dict:
        key = os.environ.get(self.env_key)
        if not key:
            raise ProviderError(self.name, f"{self.name} provider not configured",
                                f"set {self.env_key} in environment variables")
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # network/HTTP/JSON failures become typed errors
            raise ProviderError(self.name, f"provider call failed: {exc}") from exc

    @staticmethod
    def _flatten(prompt_layers: dict) -> str:
        parts = []
        for key in ("system_identity", "safety_policy", "agent_role",
                    "skill_instructions", "constitution", "memories",
                    "personal_state", "task_context", "output_contract"):
            value = prompt_layers.get(key)
            if value:
                parts.append(f"## {key}\n{json.dumps(value, ensure_ascii=False, default=str)}")
        return "\n\n".join(parts)

class OpenAIProvider(_HTTPJSONProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def complete(self, prompt_layers: dict, *, max_tokens: int = 800) -> dict:
        body = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": self._flatten(prompt_layers)}]}
        data = self._post(body, {"Authorization": f"Bearer {os.environ[self.env_key]}"})
        return {"provider": self.name, "model": body["model"],
                "text": data["choices"][0]["message"]["content"]}

class AnthropicProvider(_HTTPJSONProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    endpoint = "https://api.anthropic.com/v1/messages"

    def complete(self, prompt_layers: dict, *, max_tokens: int = 800) -> dict:
        body = {"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                "max_tokens": max_tokens, "system": self._flatten(prompt_layers),
                "messages": [{"role": "user", "content": "respond within the output contract"}]}
        data = self._post(body, {"x-api-key": os.environ[self.env_key],
                                 "anthropic-version": "2023-06-01"})
        return {"provider": self.name, "model": body["model"],
                "text": "".join(b.get("text", "") for b in data.get("content", []))}

class GeminiProvider(_HTTPJSONProvider):
    name = "gemini"
    env_key = "GEMINI_API_KEY"

    def complete(self, prompt_layers: dict, *, max_tokens: int = 800) -> dict:
        self.endpoint = ("https://generativelanguage.googleapis.com/v1beta/models/"
                         f"{os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')}:generateContent"
                         f"?key={os.environ.get(self.env_key, '')}")
        body = {"contents": [{"parts": [{"text": self._flatten(prompt_layers)}]}],
                "generationConfig": {"maxOutputTokens": max_tokens}}
        data = self._post(body, {})
        return {"provider": self.name,
                "model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
                "text": data["candidates"][0]["content"]["parts"][0]["text"]}

PROVIDERS = {p.name: p for p in (DemoProvider, OpenAIProvider, AnthropicProvider, GeminiProvider)}

def get_provider() -> BaseProvider:
    """Resolve the configured provider from AI_PROVIDER; fall back to demo."""
    name = (os.environ.get("AI_PROVIDER") or "demo").strip().lower()
    provider_cls = PROVIDERS.get(name, DemoProvider)
    provider = provider_cls()
    if not provider.available():
        return DemoProvider()
    return provider
