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
- **Approvals.** A SENSITIVE call writes a request and the task waits (WAITING_APPROVAL). The
  Chairman decides once; a second decision is a 409. Approve → the task continues and the agent
  is checked again at that moment. Reject → the task fails with "rejected by Chairman". A request
  whose task is cancelled first becomes CANCELLED ("withdrawn") — never "rejected", because
  nobody decided. An approval can be used exactly once.
- **A tool that is not built answers "not available yet".** It is never simulated.
- **A refused or failed tool call fails the task** with the reason. (There is no AI model yet
  that could react to a refusal and try something else.)
- **The audit log is append-only**: the application only inserts, there is no update or delete
  API, and database triggers refuse UPDATE and DELETE. Entries are not foreign keys to agents or
  tasks, so they outlive them. Passwords, tokens and API keys never reach it; the typed username
  of a failed login is not stored (people type passwords into that field).
- **The Central Manager delegates through `task.create_child`** like any other agent, so its
  routing is permission-checked and audited too.
- **Memory scopes** (`backend/app/memory.py`). VILLAGE: read with "Read village memory", write with
  "Write village memory". UPAZILA: only the agent's OWN Upazila, with "Read / Write Upazila
  memory". AGENT: its own notes — always readable, writable with "Keep its own notes". An agent
  cannot name another owner: the tools have no such argument. The Chairman sees and edits all.
- **No customer data in VILLAGE memory.** A memory is marked as customer data by its writer or
  when the text holds an e-mail address or a phone number; the application refuses that in
  VILLAGE scope (for agents and for the Chairman) and a CHECK constraint refuses it again.
- **Task context is temporary**: it belongs to one task and is deleted when the task ends.
- **Schedules only create tasks.** APScheduler (3.x, in-process, job store in the same SQLite
  database, the village's timezone — Asia/Dhaka by default, coalesce on, one instance per job)
  never does work itself; the task runner does, with the same checks as for any task.
- **One scheduled run, at most one task**: the run is identified by its scheduled time and that
  key is UNIQUE. After downtime the missed runs of a schedule are ONE run, at the next start.
- **A scheduled task goes straight to its agent** (task kind `scheduled`); it is not routed by
  the Central Manager. The two built-in jobs are system tasks the runner does itself: the health
  check and the daily report (counted from the database, written by no model).
- **Never rebuild the `task` table in a migration.** SQLite's batch mode drops the old table, and
  with foreign keys on that cascades to messages and approvals.

## Dashboard and map (M5)

- **Every number is an SQL count taken when the page asks.** Nothing is cached, estimated or
  hard-coded. Task numbers count every task row except the scheduler's health checks.
- **The activity feed is derived, not stored**: it is built per request from the audit log and
  the tasks' timestamps. Its links are paths inside the app.
- **An agent's activity is derived, not stored**: offline (paused/disabled) → waiting (a task in
  WAITING_APPROVAL) → working (a task RUNNING) → idle. "Waiting" wins over "working".
- **One table maps the 15 agent templates to a robot** (`frontend/src/components/robots/roles.ts`);
  a backend test fails when a template is missing there. The wellness robot is always labelled
  "assistant only".
- **The map shows ONE level at a time** (Village → Upazila → Union → Ward), never all offices at
  once, and `GET /api/map` returns one level per request.
- **Map positions are computed from counts**, never from names (`components/map/layout.ts`).
- **Map and avatars are hand-made SVG.** No images, no CDN, no map, game or 3D library.
- **The level is in the address** (`/map?level=&id=`, `&view=list`), shared by the map and its
  list view, so Back, reload and links work.
- **Refresh is polling** (10 s) through one hook that stops while the tab is hidden. No WebSockets.
- **Animations are CSS only**, so the global `prefers-reduced-motion` rule stops all of them.
