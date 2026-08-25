# Ourex Personal OS

This repository contains a dependency-free, runnable vertical slice of the Personal Operating System described in the master prompt. It intentionally separates the interface from the core API so additional interfaces (Telegram, mobile, voice, email) can use the same source of truth.

## Current implementation

- **Command Center:** answers “What matters now?” with an objective, priorities, capacity, cognitive load, insights and relationship attention.
- **Entity views:** projects, tasks/open loops, relationships, idea garden, research, reviews, governed memory, agents/skills and system control.
- **Quick capture:** task, idea or note capture from any view; persisted through the API and event logged.
- **Task execution:** completion is permission-safe in this slice, persisted through the API and emitted as an event.
- **Core API:** `/api/state`, `/api/capture`, `/api/tasks/:id`, `/api/health`.
- **Persistence:** `data.json` is a local development store. Replace the repository with a tenant-scoped database adapter in production.

## Target architecture

```text
Interfaces (Web / Mobile / Telegram / Voice / Email / API)
                         |
                     Personal OS API
                         |
       Identity · Events · Permissions · Audit · Integrations
                         |
 Context Engine — Memory Governance — Personal/Life Graph
                         |
 AI Orchestrator (intent → retrieval → risk → plan → execute → verify)
                         |
     Agents — Skills (versioned) — Tools (permissioned/MCP)
                         |
          Workflow Engine + durable async jobs
                         |
 Projects · Goals · Relationships · Research · Learning · Ideas
                         |
                   Notifications + Reviews
```

## Production boundaries

- Every external write must be classified (L0–L3), checked against user/agent/skill/tool/workflow/integration permissions, made idempotent and written to an audit log.
- Memory records must carry source, provenance, timestamp, confidence, importance, scope and optional expiry. Uncertain extraction is never promoted to identity memory without confirmation.
- AI prompts should be composed from system policy, agent role, skill contract, constitution, retrieved memories, current state and task context. Never send the complete database to a model.
- Expensive work belongs in a durable queue. Integrations implement connect/authenticate/validate/read/write/subscribe/receive-events/error/disconnect.
- Telegram and Bale belong behind messaging adapters; neither is allowed to become domain logic.
- The browser uses relative API URLs, so the UI is portable behind a reverse proxy and never depends on localhost.

## Run

```bash
python3 server.py
# open http://localhost:8000
```

Set `PORT` to use another port. `data.json` is generated on first run and is intentionally ignored by Git.
