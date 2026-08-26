# Environment variables

Ourex reads all configuration from environment variables. **Never commit
secrets to this repository.** Every integration runs in a truthful simulator
mode when its variables are absent and reports exactly which variable it
needs (see `/api/integrations/status`).

## Core

| Variable | Required | Purpose |
| --- | --- | --- |
| `PORT` | no | local dev server port (default `8000`) |
| `PERSONAL_OS_DB` | no | SQLite path (or `:memory:`). Default: `./personal_os.sqlite3` locally, `/tmp/personal_os.sqlite3` on Vercel. Point at durable storage for production persistence. |
| `PERSONAL_OS_TOKEN` | no | if set, all **mutating** API calls require `Authorization: Bearer <token>` |
| `AI_PROVIDER` | no | `demo` (default, offline) · `openai` · `anthropic` · `gemini` |

## Model providers (used only when `AI_PROVIDER` selects them)

| Variable | Provider |
| --- | --- |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | OpenAI (also powers voice STT via Whisper) |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Anthropic |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini |

## Messaging integrations

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram send capability + live webhook mode |
| `TELEGRAM_WEBHOOK_SECRET` | verifies `X-Telegram-Bot-Api-Secret-Token` on `/api/integrations/telegram/webhook` |
| `BALE_BOT_TOKEN` | Bale send capability |
| `BALE_WEBHOOK_SECRET` | verifies the Bale webhook |

## Tools (optional; enable live mode)

| Variable(s) | Tool |
| --- | --- |
| `CALENDAR_PROVIDER`, `CALENDAR_CREDENTIALS_JSON` | calendar |
| `EMAIL_IMAP_HOST`, `EMAIL_SMTP_HOST`, `EMAIL_CREDENTIALS_JSON` | email |
| `SEARCH_API_KEY` | search |
| `FINANCE_PROVIDER`, `FINANCE_CREDENTIALS_JSON` | finance (L3 — always approval-gated) |

## Vercel setup

1. Vercel Dashboard → Project → Settings → Environment Variables: add the
   variables you need (production scope).
2. No build command or output directory is required. `/api/*.py` deploys as
   Python serverless functions automatically; the repository root serves as
   static assets.
3. Serverless persistence is ephemeral per warm instance. For durable data:
   set `PERSONAL_OS_DB` to a mounted path if you attach Vercel Storage, or
   swap the storage adapter (see `docs/ARCHITECTURE.md`).

## Verifying a deployment

```bash
curl https://<your-deployment>/api/health
curl https://<your-deployment>/api/state | head
curl -X POST https://<your-deployment>/api/core/workflows/run \
  -H 'Content-Type: application/json' -d '{"name":"relationship-follow-up"}'
# expect HTTP 202 with an approval request — risk 2+ never runs silently
```
