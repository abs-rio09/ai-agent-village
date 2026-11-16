# Decisions

The decisions this project is built on. The first section is fixed by the owner (the same list
as `CLAUDE.md`; if the two ever differ, `CLAUDE.md` wins and this file must be corrected).
The later sections record choices made while building; they can be changed, but only on purpose.

## Fixed decisions (do not change without the owner)

| # | Decision |
|---|----------|
| F1 | Local-first, single user. One Ubuntu PC (Ryzen 7 5700G, 8 GB RAM). Keep dependencies light. |
| F2 | Python >= 3.12, Node >= 20. |
| F3 | Backend: FastAPI + Pydantic v2 + SQLAlchemy 2 (typed `Mapped[]`) + Alembic. |
| F4 | Database: SQLite in WAL mode. No Postgres, Redis, Docker or any other server. |
| F5 | Frontend: React + TypeScript + Vite + Tailwind + Lucide + React Router. Tests: Vitest + RTL. No Playwright in the repo. |
| F6 | One process: a single uvicorn worker on `http://127.0.0.1:8000` serves `/api` and the built frontend. |
| F7 | Bind to 127.0.0.1 only. The configuration rejects any non-loopback host. Remote access is only through a local proxy (Tailscale), see `docs/MOBILE.md`. |
| F8 | Never use sudo and never install system packages; print the exact `apt` command instead. |
| F9 | Demo Mode must work with no API key. Never claim Ollama or Anthropic works unless it was tested with real credentials. |
| F10 | Secrets live in `data/.env` (mode 600) — never in the database, the logs or an API response. |
| F11 | Every schema change is an Alembic migration. Never `create_all()`. Timestamps are stored as naive UTC. |
| F12 | Everything under `/api` needs a session unless its path is on the public allowlist in `security.py`. |
| F13 | No fake data in the UI. An unbuilt page says "Coming in M<n>". A feature is only called working when it was run or tested. |
| F14 | Work one milestone part at a time; `docs/SPEC.md` describes features, not the build order. |

## Organisation and agents (M2, M3)

- A Union holds at most 9 Wards (`backend/app/limits.py`).
- An agent stores only its Office; Upazila, Union and Ward are derived from it.
- There is exactly one Central Manager. It routes and reports; it never does delegated work.
  It cannot be paused, disabled, deleted or moved.
- Routing in Demo Mode is keyword matching (`backend/app/routing_keywords.py`), not understanding.
- An agent with history (tasks or messages) cannot be deleted, only disabled.
- Deleting a Ward, Union or Upazila keeps its agents: they lose the Office and are disabled.
- Delegation is at most 3 levels deep.

## Control (M4)

- **One registry, one check.** Every tool is registered in `backend/app/tools`. The only way to
  run one is `call_tool`, and the only permission check is `check_tool_use(agent, tool)`: the
  agent must be ACTIVE, the tool must be assigned to it, and it must hold the permission the
  tool needs. The check reads the agent's own row and nothing else, so no task text, message or
  tool argument can grant a tool.
- **Tool keys are `area.verb`** (`task.create_child`). The free-form M3 keys were renamed by
  migration 0007. Existing agents only got the rename; no migration assigns a tool to an agent.
- **No shell, no free file access, no network tool.** A tool gets the calling agent, its task
  and a database session — nothing else.
- **SENSITIVE tools always need the Chairman's approval** and are never a template default, and
  neither are the permissions they require. The four that exist (`message.send_external`,
  `file.delete`, `money.spend`, `marketing.publish`) are placeholders: there is no connector
  behind them, and they say so.
- **A tool that is not built answers "not available yet".** It is never simulated.
- **A refused or failed tool call fails the task** with the reason. (There is no AI model yet
  that could react to a refusal and try something else.)
- **The audit log is append-only**: the application only inserts, there is no update or delete
  API, and database triggers refuse UPDATE and DELETE. Entries are not foreign keys to agents or
  tasks, so they outlive them. Passwords, tokens and API keys never reach it; the typed username
  of a failed login is not stored (people type passwords into that field).
- **The Central Manager delegates through `task.create_child`** like any other agent, so its
  routing is permission-checked and audited too.
