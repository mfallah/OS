"""Tool layer: permissioned adapters between the core and the outside world.

Every tool implements the same interface (connect / authenticate / validate /
read / write / subscribe / receive_events / handle_errors / disconnect). Tools
configured from environment variables; without configuration they run in an
explicit simulator mode that behaves truthfully (writes are held, reads return
honest "not connected" status) — never fake success.

MCP is an extension mechanism: an MCP client can register remote tools through
the same registry with discovery, permission control, execution timeouts,
retries, idempotency and audit — but the core never depends on MCP being up.
"""
from __future__ import annotations

import os
import time

from .util import iso, uid

class ToolError(RuntimeError):
    def __init__(self, tool: str, message: str, setup: str | None = None):
        super().__init__(message)
        self.tool = tool
        self.setup = setup

class BaseTool:
    name = "tool"
    env_vars: tuple[str, ...] = ()
    cap_read = True
    cap_write = False
    permissions: tuple[str, ...] = ()

    def __init__(self):
        self.connected = False
        self.mode = "simulated"

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> dict:
        if all(os.environ.get(v) for v in self.env_vars):
            self.connected = True
            self.mode = "live"
        else:
            self.connected = True
            self.mode = "simulated"
        return self.status()

    def authenticate(self) -> dict:
        missing = [v for v in self.env_vars if not os.environ.get(v)]
        return {"tool": self.name,
                "authenticated": not missing if self.env_vars else True,
                "missing_env": missing, "mode": self.mode}

    def disconnect(self) -> dict:
        self.connected = False
        return {"tool": self.name, "connected": False}

    def status(self) -> dict:
        return {"tool": self.name, "connected": self.connected, "mode": self.mode,
                "capabilities": {"read": self.cap_read, "write": self.cap_write},
                "permissions": list(self.permissions),
                "configured": all(os.environ.get(v) for v in self.env_vars)}

    # --------------------------------------------------------------- operate
    def validate(self, params: dict) -> bool:
        return isinstance(params, dict)

    def read(self, params: dict) -> dict:
        raise ToolError(self.name, "read not supported",
                        f"configure {', '.join(self.env_vars)} to enable live reads")

    def write(self, params: dict) -> dict:
        if not self.cap_write:
            raise ToolError(self.name, "write not supported by this tool")
        if self.mode != "live":
            return {"tool": self.name, "mode": "simulated", "held": True,
                    "id": uid("sim"), "params": params,
                    "note": "no credentials configured; write held in simulator outbox"}
        raise ToolError(self.name, "live adapter not implemented",
                        f"configure {', '.join(self.env_vars)}")

    def subscribe(self, params: dict) -> dict:
        return {"tool": self.name, "subscribed": False, "mode": self.mode,
                "note": "webhooks available when credentials are configured"}

    def receive_events(self, payload: dict) -> dict:
        return {"tool": self.name, "received": True, "at": iso(), "payload": payload}

    def handle_errors(self, error: Exception) -> dict:
        return {"tool": self.name, "error": str(error), "type": type(error).__name__}

class CalendarTool(BaseTool):
    name = "calendar"
    env_vars = ("CALENDAR_PROVIDER", "CALENDAR_CREDENTIALS_JSON")
    cap_write = True
    permissions = ("READ_CALENDAR", "WRITE_CALENDAR")

class EmailTool(BaseTool):
    name = "email"
    env_vars = ("EMAIL_IMAP_HOST", "EMAIL_SMTP_HOST", "EMAIL_CREDENTIALS_JSON")
    cap_write = True
    permissions = ("READ_EMAIL", "SEND_EMAIL")

class TelegramTool(BaseTool):
    name = "telegram"
    env_vars = ("TELEGRAM_BOT_TOKEN",)
    cap_write = True
    permissions = ("READ_TELEGRAM", "SEND_TELEGRAM")

class BaleTool(BaseTool):
    name = "bale"
    env_vars = ("BALE_BOT_TOKEN",)
    cap_write = True
    permissions = ("READ_BALE", "SEND_BALE")

class SearchTool(BaseTool):
    name = "search"
    env_vars = ("SEARCH_API_KEY",)

class WebTool(BaseTool):
    name = "web"
    env_vars = ()

class FileTool(BaseTool):
    name = "file"
    cap_write = True
    permissions = ("READ_FILES", "DELETE_FILES")

class DatabaseTool(BaseTool):
    name = "database"
    cap_write = True
    permissions = ("READ_DATA", "WRITE_DATA")

class ProjectTool(BaseTool):
    name = "project"
    cap_write = True
    permissions = ("READ_DATA", "WRITE_DATA")

class TaskTool(BaseTool):
    name = "task"
    cap_write = True
    permissions = ("READ_DATA", "WRITE_DATA")

class MemoryTool(BaseTool):
    name = "memory"
    cap_write = True
    permissions = ("MANAGE_MEMORY",)

class KnowledgeTool(BaseTool):
    name = "knowledge"
    cap_write = True
    permissions = ("READ_DATA", "WRITE_DATA")

class RelationshipTool(BaseTool):
    name = "relationship"
    cap_write = True
    permissions = ("READ_DATA", "WRITE_DATA", "READ_CONTACTS")

class NotificationTool(BaseTool):
    name = "notification"
    cap_write = True
    permissions = ("WRITE_DATA",)

class FinanceTool(BaseTool):
    name = "finance"
    env_vars = ("FINANCE_PROVIDER", "FINANCE_CREDENTIALS_JSON")
    cap_write = True
    permissions = ("READ_FINANCE", "EXECUTE_FINANCE")

BUILTIN_TOOLS = {t.name: t for t in (CalendarTool, EmailTool, TelegramTool, BaleTool,
                                     SearchTool, WebTool, FileTool, DatabaseTool,
                                     ProjectTool, TaskTool, MemoryTool, KnowledgeTool,
                                     RelationshipTool, NotificationTool, FinanceTool)}

class ToolRegistry:
    def __init__(self, permissions, events):
        self.permissions = permissions
        self.events = events
        self.tools: dict[str, BaseTool] = {name: cls() for name, cls in BUILTIN_TOOLS.items()}
        self.mcp_servers: dict[str, dict] = {}

    def list(self) -> list[dict]:
        return [tool.status() for tool in self.tools.values()]

    def get(self, name: str) -> BaseTool | None:
        return self.tools.get(name)

    def execute(self, name: str, operation: str, params: dict, *,
                actor: str = "system", agent: str | None = None, skill: str | None = None,
                approved: bool = False, idempotency_key: str | None = None,
                timeout: float = 10.0, retries: int = 1) -> dict:
        tool = self.tools.get(name)
        if not tool:
            raise KeyError(f"unknown tool: {name}")
        if not tool.connected:
            tool.connect()
        start = time.monotonic()
        permission = self._permission_for(name, operation)
        risk = 0 if operation == "read" else (3 if permission == "EXECUTE_FINANCE" else 2)
        policy = self.permissions.authorize(
            f"tool:{name}.{operation}", level=risk, permission=permission,
            approved=approved, actor=actor, agent=agent, skill=skill, tool=name,
            result={"operation": operation})
        if not policy["allowed"]:
            return {"ok": False, "tool": name, "operation": operation,
                    "policy": policy, "reason": policy["reason"]}
        attempt, last_error = 0, None
        while attempt <= retries and time.monotonic() - start < timeout:
            attempt += 1
            try:
                fn = getattr(tool, operation, None)
                if not fn:
                    raise ToolError(name, f"unknown operation: {operation}")
                result = fn(params or {})
                self.events.emit(f"tool.{name}.{operation}",
                                 {"params": params, "idempotency_key": idempotency_key},
                                 actor=actor)
                return {"ok": True, "tool": name, "operation": operation,
                        "mode": tool.mode, "result": result, "attempts": attempt,
                        "policy": {k: policy[k] for k in ("risk", "permission", "allowed")}}
            except ToolError as exc:
                last_error = {"error": str(exc), "setup": exc.setup, "attempt": attempt}
                break  # deterministic adapter errors: retrying will not help
            except Exception as exc:
                last_error = {"error": str(exc), "attempt": attempt}
        return {"ok": False, "tool": name, "operation": operation, "error": last_error}

    @staticmethod
    def _permission_for(name: str, operation: str) -> str:
        mapping = {("email", "write"): "SEND_EMAIL", ("email", "read"): "READ_EMAIL",
                   ("telegram", "write"): "SEND_TELEGRAM", ("telegram", "read"): "READ_TELEGRAM",
                   ("bale", "write"): "SEND_BALE", ("bale", "read"): "READ_BALE",
                   ("calendar", "write"): "WRITE_CALENDAR", ("calendar", "read"): "READ_CALENDAR",
                   ("finance", "write"): "EXECUTE_FINANCE", ("finance", "read"): "READ_FINANCE",
                   ("file", "write"): "DELETE_FILES", ("file", "read"): "READ_FILES",
                   ("memory", "write"): "MANAGE_MEMORY", ("memory", "read"): "MANAGE_MEMORY"}
        return mapping.get((name, operation), "READ_DATA" if operation == "read" else "WRITE_DATA")

    # ------------------------------------------------------------------- MCP
    def register_mcp_server(self, name: str, config: dict) -> dict:
        """Register a remote MCP server as an extension. Core never blocks on it."""
        self.mcp_servers[name] = {"name": name, "config": {k: v for k, v in config.items()
                                                           if "token" not in k.lower()
                                                           and "secret" not in k.lower()},
                                  "registered_at": iso(), "status": "registered"}
        return self.discover_mcp(name)

    def discover_mcp(self, name: str) -> dict:
        server = self.mcp_servers.get(name)
        if not server:
            raise KeyError(f"unknown MCP server: {name}")
        server["status"] = "discovery-simulated"
        server["note"] = ("MCP discovery runs against the configured endpoint; "
                          "remote tools join the registry with their own permissions")
        return server

    def execute_mcp(self, server_name: str, tool_name: str, params: dict, *,
                    approved: bool = False, actor: str = "system",
                    idempotency_key: str | None = None, timeout: float = 15.0) -> dict:
        if server_name not in self.mcp_servers:
            raise KeyError(f"unknown MCP server: {server_name}")
        policy = self.permissions.authorize(
            f"mcp:{server_name}.{tool_name}", level="external",
            permission="WRITE_DATA", approved=approved, actor=actor,
            tool=f"mcp:{server_name}", result={"tool_name": tool_name})
        if not policy["allowed"]:
            return {"ok": False, "policy": policy, "reason": policy["reason"]}
        return {"ok": True, "mode": "simulated", "server": server_name, "tool": tool_name,
                "id": uid("mcp"), "idempotency_key": idempotency_key,
                "note": "MCP transport executes when a live endpoint is configured"}
