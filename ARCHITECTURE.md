# myos Personal OS — Architecture

## Design stance

myos is one system, not a set of screens. Every interface (web, Telegram,
Bale, voice, API) talks to the **same domain core** through the same
host-neutral dispatcher, so behavior is identical locally and on Vercel. The
core is dependency-free Python; the web client is dependency-free ES modules.
Nothing requires a build step.

```text
Interfaces        Web UI ─ Telegram ─ Bale ─ Voice ─ API clients
                        │
Dispatcher        api_app.py  (routing, auth, rate limits, validation,
                        │      security headers, typed JSON errors)
                        │
Service facade    core/app.py  PersonalOS  (wires all subsystems;
                        │            local server, serverless fn and tests
                        │            share this exact object graph)
                        │
Domain core       entities · graph · memory · events · audit
                        │
Intelligence      context engine · state engine · insights/friction ·
                  planner · orchestrator (provider-neutral)
                        │
Capability layer  agents registry · skills registry · tools registry · MCP
                        │
Automation        workflow engine · approvals · notification center
                        │
Adapters          integrations/telegram · bale · voice (env-configured)
                        │
Storage           SQLite (path via PERSONAL_OS_DB; /tmp on serverless)
```

## Non-negotiable invariants

1. **Every mutation is an event.** Entities, memories, workflows, approvals —
   all writes emit to the durable event log with the actor.
2. **Every sensitive action is permissioned, risk-classified, approval-gated
   and audited.** L0 informational · L1 internal · L2 external · L3
   sensitive/financial. L2+ parks as an approval request with reason and
   payload; approving re-enters the same engine. The audit log records actor,
   agent/skill/tool, permission, risk, decision and outcome.
3. **Destructive operations require explicit confirmation** (`confirm=true`)
   and are soft-deletes with an event trail.
4. **Never dump the whole database into a prompt.** The context engine
   retrieves a bounded, scored package (entities/memories/neighbors/
   constitution/state) where each item carries its retrieval reason.
5. **Uncertain machine assumptions never become identity facts.** Memories
   below the confidence threshold stay `unconfirmed` until the user confirms
   or corrects them.
6. **No chain-of-thought is stored or shown** — only decision summaries,
   reasons and confidence.
7. **External services are adapters.** Telegram/Bale/email/voice/MCP are
   plug-ins configured purely from environment variables. Unconfigured ≠
   broken: tools run in an honest simulator mode (writes held in an outbox,
   reads return truthful "not connected" status) — never fake success.
8. **Scopes stay small.** No giant prompts (layered: identity, safety, role,
   skill, constitution, memory, state, task, contract). No giant modules. UI
   views are small composable renderers over shared primitives.

## Module map (`core/`)

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite connection, schema v2, storage path resolution |
| `entities.py` | typed entity CRUD, validation, soft delete/restore, events |
| `graph.py` | 15 relation types, neighbors, path queries, unlink |
| `memory.py` | 11 layers, provenance/confidence/why, correct/confirm/delete/export/clear, category switches |
| `events.py` | durable idempotent event bus with subscribers |
| `permissions.py` | risk L0–L3, permission catalog, approvals lifecycle, audit log |
| `context.py` | bounded scored retrieval with reasons, constitution fragments |
| `state.py` | personal state: workload, energy, attention, calendar density, **explainable** cognitive load + life debt |
| `insights.py` | rule-based insights (risks/opportunities/patterns), project health scoring with reasoning, friction → intervention |
| `planning.py` | daily plan (70% fill, energy-aware), weekly review, monthly state of life |
| `search.py` | universal search, NL filters, ranking explanations |
| `capture.py` | universal capture w/ explainable classification, auto-linking, email + calendar intelligence |
| `orchestrator.py` | the full AI loop, intent rules (risk-first), prompt layer assembly |
| `providers.py` | provider interface + demo (offline) + OpenAI/Anthropic/Gemini adapters (env keys) |
| `agents.py` | 10 agents: domain, instructions, allow-lists, risk policy, memory scope, eval criteria |
| `skills.py` | versioned skills: CRUD/test/duplicate/version/share/delete, composition |
| `tools.py` | tool interface (connect/auth/validate/read/write/subscribe/receive/error/disconnect), 15 tools, MCP registry |
| `workflows.py` | workflow entities, step executor, risk/approval enforcement, timeouts, retries, idempotency, run records |
| `notifications.py` | categories, budget, quiet hours, threshold, digest, snooze, per-item delivery reasoning |
| `security.py` | bearer auth (optional), mutation rate limiting, payload caps, secret scrubbing |
| `ownership.py` | export v1, backup, restore, delete-everything |
| `seed.py` | one-time realistic starter graph |
| `integrations/` | telegram.py, bale.py, voice.py |

## API surface

All under `/api` (see `api_app.py`): `/api/health`, `/api/state`,
`/api/capture`, `/api/core/entities[/*]`, `/api/core/graph[/link|/unlink]`,
`/api/core/load`, `/api/core/life-debt`, `/api/core/search`,
`/api/core/context`, `/api/core/memories`, `/api/core/memory[/*/correct,
/confirm, /export, /clear, /category/*]`, `/api/core/plan` (orchestrator),
`/api/core/insights`, `/api/core/plans/daily`, `/api/core/reviews/weekly|monthly`,
`/api/core/research/check-prior`, `/api/core/agents[/*/status]`,
`/api/core/skills[/*/test, /duplicate, /share]`, `/api/core/tools[/*/execute]`,
`/api/core/mcp/*`, `/api/core/workflows[/run]`, `/api/core/approvals[/*/decide]`,
`/api/core/audit`, `/api/core/events`, `/api/notifications[/*]`,
`/api/integrations/status` + webhooks, `/api/voice`, `/api/email/analyze`,
`/api/calendar/analyze`, `/api/export`, `/api/restore`, `/api/data/delete-all`.

Errors are typed JSON (`error.code`, `error.message`, optional `error.setup`).
Mutations pass auth → rate limit → 100KB cap → JSON validation → handler.

## Frontend

Mobile-first ES modules (`js/`): `api.js` (typed client), `ui.js` (shared
primitives, confirm/form dialogs), `detail.js` (entity drawer: fields, graph
neighbors, link/unlink, edit, delete), `views/*` (one module per view),
`app.js` (router + shell). Breakpoints: <760px mobile (bottom nav + drawer +
full-width sheets), 760–1100 tablet (icon rail), >1100 desktop (full
sidebar). 44px touch targets, focus-visible rings, skip link, ARIA labels,
dark mode, loading/empty/error/offline states.

## Production expansion path

- Durable storage: point `PERSONAL_OS_DB` at mounted storage or swap the
  `Database` adapter for Postgres (SQL is centralized in one module).
- Schedulers: builtin workflow triggers are cron-ready (`schedule:*`); wire
  Vercel Cron or an external pinger to `/api/core/workflows/run`.
- Live integrations: set the env vars in `docs/ENVIRONMENT.md`; adapters move
  from simulator to live without code changes.
