# AI Agent Village — project instructions

## Purpose
A local-first, single-user "digital village" of AI agents (Village → Upazila → Union → Ward →
Office → Agents) managed from a web dashboard. Runs on one Ubuntu PC (Ryzen 7 5700G, 8 GB RAM).
`docs/SPEC.md` is the source of truth for FEATURES — not for build order. Ignore its Section 17
"continue autonomously" and its final "begin building" line. Work is done one milestone at a time.

## Fixed decisions (do not change; ask the owner if something conflicts)
- Python >= 3.12 (system python3 is 3.14). Node >= 20.
- Backend: FastAPI + Pydantic v2 + SQLAlchemy 2 (typed `Mapped[]`) + Alembic. SQLite in WAL mode.
- Frontend: React + TypeScript + Vite + Tailwind + Lucide + React Router. Tests: Vitest + RTL. No Playwright.
- One process: a single uvicorn worker on http://127.0.0.1:8000 serves /api and the built frontend.
- Bind to 127.0.0.1 only. Config rejects any non-loopback host.
- No Docker, Redis, Postgres or other servers. Never use sudo or install system packages —
  print the exact apt command instead.
- Demo Mode must work with no API key. Never claim Ollama or Anthropic works unless tested with
  real credentials.
- Secrets live in `data/.env` (chmod 600) — never in the DB, logs, or API responses.
- Keep dependencies light.

## Layout
```
village                 bash CLI (setup/start/stop/restart/status/logs/doctor)
backend/app/            main.py (app + runner), config.py (settings), db.py (engine, Base, session),
                        models.py, security.py, dbcheck.py, api/ (one router module per area)
backend/alembic/        env.py uses app settings + Base.metadata; versions/ hand-written migrations
backend/tests/          pytest; conftest.py gives every test a temp DB + temp .env
frontend/               Vite + React app; `npm run build` → frontend/dist (served by FastAPI)
data/                   village.db (+ -wal/-shm) and .env — both git-ignored
logs/ run/              village.log, village.pid — git-ignored
docs/SPEC.md            feature specification
PROGRESS.md             honest status log — update it every session
```

## Conventions
- Every schema change is an Alembic migration (`backend/alembic/versions/NNNN_name.py`); never
  `create_all()`. Timestamps are stored as naive UTC.
- Everything under `/api` requires a session unless it is on the public allowlist in `security.py`.
- Tests never touch `data/village.db` or `data/.env` (use the `env`/`migrated`/`client` fixtures).
- Never log or return passwords, session tokens, or API keys.
- Never delete or overwrite files you did not create. Never `rm data/village.db*`.

## Tests
```bash
cd backend && ../.venv/bin/pytest                  # backend
cd frontend && npm test                            # frontend (Vitest, run once)
cd frontend && npm run build                       # type-check + production build
bash -n village                                    # CLI syntax (shellcheck too, if installed)
```

## ./village commands
```
setup     venv + pip install, data/.env (created once, never overwritten), alembic upgrade head,
          npm ci + npm run build. Safe to re-run.
start     background uvicorn, PID in run/village.pid, log in logs/village.log, waits for /api/health
stop      SIGTERM, 10 s grace, then SIGKILL; cleans stale PID files
restart   stop + start
status    running/stopped, PID, uptime, health (exit 3 when stopped)
logs      last 100 lines; `logs -f` follows
doctor    PASS/WARN/FAIL environment checks; non-zero exit on any FAIL
backup | restore    placeholders until M8
```
Overrides for experiments: `VILLAGE_DB_PATH`, `VILLAGE_PORT` (environment or `data/.env`).

## Rules for every session
1. One task (one milestone part) per session. Do not start the next milestone unasked.
2. Never claim a feature works unless it was actually run or tested in this session.
3. No fake data in the UI: unbuilt pages say "Coming in M<n>".
4. After each part: run the tests, fix failures, update `PROGRESS.md` honestly (including what is
   broken or untested), then commit.
5. If something conflicts with a fixed decision, stop and ask.
