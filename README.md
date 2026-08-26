# myos — Personal OS

An AI-native personal operating system: one source of truth for your entities,
graph, governed memory, workflows and approvals — with an explainable chief of
staff on top, not another dashboard.

Everything the system does is grounded in real subsystems: a SQLite domain core,
typed entities with a personal graph, provenance-carrying memories, an event
log, a permission/risk/approval engine, a bounded context engine, and an
audited workflow runtime. The UI is a fully wired client of the same API —
no mock screens.

## What it does today

- **Command Center** — answers "What matters now?" with your main objective,
  top priorities, a capacity-aware daily plan (70% fill rule, slack protected),
  explained cognitive load and life debt, AI insights with confidence +
  reasoning, relationship attention, project health, decisions waiting on you,
  calendar context, recent changes and a recommended next action.
- **Entities & Graph** — 40+ typed entity kinds; any entity links to any other
  via 15 relation types (`supports`, `blocks`, `depends_on`, …). Create, edit,
  soft-delete and connect everything from the UI.
- **Memory Governance** — layered memory with source, provenance, confidence,
  importance, scope, expiry and *why remembered*. Uncertain assumptions stay
  **unconfirmed** until you promote them. Correct, delete, export, clear, or
  disable whole categories.
- **Workflows & Approvals** — 11 builtin workflows (morning brief, evening
  review, weekly executive review, monthly state of life, …). Risk-2+ actions
  never run silently: they create approval requests; approving re-executes
  through the same audited engine.
- **Orchestrator** — intent → context → risk → plan → agent/skill/tool →
  execution → verification → memory → audit → response. Provider-neutral
  (demo/OpenAI/Anthropic/Gemini via env), layered prompts — never one giant
  prompt, never the whole database.
- **Agents / Skills / Tools** — 10 agents, versioned skills (create, edit,
  test, duplicate, disable, share), tools with an honest simulator mode when
  credentials aren't configured, and MCP as a real extension mechanism.
- **Search** — universal, with natural-language filters (`kind:task due:today`,
  `high priority research`) and per-result ranking explanations.
- **Integrations** — Telegram and Bale two-way adapters (commands, capture,
  briefs, approvals), a voice pipeline with STT provider + text fallback, and
  webhook verification via env secrets.
- **Data ownership** — full export/restore, audit history, event stream,
  explicit-confirmed deletes.

## Run locally

```bash
python3 server.py          # → http://localhost:8000
npm start                  # same thing
```

The server binds `0.0.0.0` and reads `PORT`. Data lives in
`personal_os.sqlite3` (gitignored) or wherever `PERSONAL_OS_DB` points.

## Deploy to Vercel

Push to `main`. The repo is ready as-is:

- Static frontend served from the repository root (`index.html`, `styles.css`, `js/`).
- One Python serverless function `api/index.py` handles every `/api/*` route
  (rewritten in `vercel.json`) through the same dispatcher as local dev.
- Python-only runtime in `/api` — no Node/Python conflict, no build step,
  no dependencies (`requirements.txt` intentionally absent).

Persistence note: serverless instances are ephemeral. Set `PERSONAL_OS_DB`
(or wire a remote storage adapter) for durable production data; otherwise each
warm instance keeps its own SQLite in `/tmp` and re-seeds on cold start.

## Environment variables

See [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md). No secret ever belongs in
this repo; integrations report which env var they need.

## Checks & tests

```bash
npm run check      # JS syntax + Python compile + all tests
```

56 unit/integration tests cover entities, graph, memory, permissions,
approvals, workflows, orchestrator, context, state, search, capture, skills,
tools/MCP, ownership and the HTTP dispatcher (`tests/test_system.py`), plus
the original v1 contract tests (`test_core.py`) which still pass unchanged.

## Layout

```
index.html styles.css js/     responsive frontend (mobile-first ES modules)
server.py                     local dev server (static + API)
api/index.py                  Vercel serverless function (same dispatcher)
api_app.py                    host-neutral API router
core/                         the domain core (see ARCHITECTURE.md)
tests/ + test_core.py         test suites
docs/                         environment & architecture notes
```
