# PROGRESS

Milestone **M1 — Foundation**: Parts A, B and C are built and committed. One acceptance item is
still open: the live run on the default port 8000 (see "Broken & known issues").

## Done
### M1 Part A — scaffold, backend core, `./village` CLI
- Project layout, `.gitignore`, `backend/requirements.txt` (installs on Python 3.14.4;
  argon2-cffi 25.1.0 has a 3.14 wheel, so no bcrypt fallback was needed).
- `config.py`: pydantic-settings, prefix `VILLAGE_`, reads `data/.env`; loopback-only host
  validation; `secret_key` required; `demo_mode` = no Anthropic key.
- `db.py`: SQLite engine with `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` on every
  connection; `Base`, session factory, `get_session` dependency.
- Alembic from day one; migration `0001` creates and seeds `app_meta`.
- `GET /api/health` (returns 503 + `db_ok:false` if the database is not migrated).
- `./village` CLI: setup, start, stop, restart, status, logs, doctor; backup/restore placeholders.
  Verified by hand on a scratch DB and port 8011: setup twice, start, refuse second start,
  status, restart, logs, stop, stale-PID cleanup.
- Tests: 24 passed, 1 skipped (shellcheck is not installed on this PC).

### M1 Part B — admin auth + first-run wizard API
- Migration `0002`: `village`, `admin_user`, `session` (also bumps `app_meta.schema_version` to 2).
- `security.py`: argon2id password hashing; session token = `secrets.token_urlsafe(32)`, only its
  sha256 is stored; cookie `village_session` (HttpOnly, SameSite=Strict, Path=/, 7 days, not
  Secure); in-memory login lockout (5 failures / 5 min per username → 429 with Retry-After).
- Endpoints: `GET /api/setup/status`, `POST /api/setup` (one transaction; 409 on a second run),
  `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET /api/village`.
- `/api` is default-deny: a router-level guard requires a session for everything except
  health, setup/status, setup and auth/login. A test enumerates all routes to enforce this.
- The Anthropic key from the wizard goes to `data/.env` only (atomic write, mode 600), is reported
  as "saved, not tested", and is never tested, stored in the DB, logged, or returned.
- Extra hardening (not in the brief, small): validation errors no longer echo the rejected input
  (FastAPI's default would have returned a bad password/API key in the 422 body); Host-header
  allowlist (DNS rebinding) and a same-origin check on state-changing `/api` calls (other local
  apps on other ports are "same-site", so SameSite=Strict alone does not stop them).
- Tests: 65 passed, 1 skipped (shellcheck). Also smoke-tested against a real server on a scratch
  DB/.env/port: setup → 409 on repeat → logout → restart → login; grep confirmed that neither the
  API key nor the password appears in the log or the database files.

### M1 Part C — React shell + wizard UI, served by FastAPI
- `frontend/`: Vite 8 + React 19 + TypeScript 7 + Tailwind 4 + Lucide + React Router 8;
  `package-lock.json` committed; dev server proxies `/api` to 127.0.0.1:8000; build → `frontend/dist`.
- FastAPI serves `frontend/dist`: static files, SPA fallback for non-`/api` paths, JSON 404 for
  unknown `/api` paths, and a "run ./village setup" page (503) when the build is missing.
- Routing: setup not done → `/setup`; not logged in → `/login`; otherwise the app shell.
- `/setup` wizard, 6 steps with Back/Next, client-side validation, password strength hint, server
  errors mapped back to the right step. `/login` page.
- App shell: dark "village control center" look, sidebar with the 22 pages of SPEC §13 in 8 groups;
  21 unbuilt pages show "Coming in M<n>" and no data. Top bar: village name, AI mode badge
  (Demo / Ollama: not tested / Anthropic: not tested), logout.
- Overview shows only real backend data (`/api/village`, `/api/health`) plus a clock in the
  village timezone. No statistics.
- Typed API client (`src/api.ts`): `credentials: 'include'`, 401 → `/login`.
- Tests: Vitest + RTL 28 passed; pytest 82 passed, 1 skipped (shellcheck). `npm run build` succeeds.
- Verified in a real (headless) browser against a scratch DB/.env on port 8011: empty-form and
  password-mismatch blocking, full wizard with an Anthropic key (fake), dashboard, a "Coming in M4"
  page, logout, wrong-password error, login, and still logged in with data intact after
  `./village restart`. Afterwards the key and password were in neither the log nor the DB files.
- Final check: `setup` ×2, `doctor`, `start`, `status`, health, `/` → 200, `restart`, `stop`,
  `status` all passed with `VILLAGE_DB_PATH=/tmp/village-m1.db` **on port 8010**
  (`VILLAGE_PORT=8010`), not on 8000 — see below.

## In progress
- Nothing. M2 has not been started.

## Broken & known issues
- **M1 is not fully accepted on port 8000.** The final check as written stops at `./village doctor`
  (`FAIL port: 8000 on 127.0.0.1 is in use by another program`). Everything was verified on other
  ports instead. To close this: stop the `api-gateway` container and re-run the final check, or
  decide on a different default port.
- **Port 8000 is occupied on this PC** by the Docker container `api-gateway` (0.0.0.0:8000), which
  belongs to another project. `./village start` on the default port fails until that container is
  stopped; `./village doctor` reports it as a FAIL. Workaround: `VILLAGE_PORT=<other>`.
- `VILLAGE_SECRET_KEY` is required and generated, but nothing uses it yet (session tokens are
  random and stored hashed). It is reserved for future signing needs.
- Demo/AI: no AI provider code exists yet. `ai_mode`, the Ollama URL and the Anthropic key are
  only stored; **neither Ollama nor Anthropic has been contacted or tested**.
- `GET /api/health` `demo_mode` follows the brief literally ("no Anthropic key set"), so a village
  in Ollama mode without a key still reports `demo_mode: true`.
- Login lockout is in memory: it resets when the server restarts. Sessions are not cleaned up
  on a schedule (expired rows are deleted at the next login).
- The owner has not yet clicked through the wizard personally; the browser verification above was
  done by the assistant in a headless browser on a scratch database, not on `data/village.db`.
- The "Coming in M<n>" numbers (M2 org structure, M3 agents + AI settings, M4 tasks/approvals/
  communication, M5 map, M6 memory + documents, M7 commerce + integrations, M8 reports, settings,
  backup, health) are an assumption — only "backup = M8" was given. They live in
  `frontend/src/nav.ts`.
- The small-screen (drawer) layout exists but was only checked at desktop width.
- `./village setup` runs `npm ci` every time, as specified, so each run reinstalls
  `node_modules` (a few seconds here).
- shellcheck is not installed, so the CLI was only checked with `bash -n`
  (`sudo apt install shellcheck` to enable that test).
- Starlette prints a deprecation warning that its TestClient will prefer `httpx2` over `httpx`;
  harmless today.

## Last session
- Built M1 Parts A, B and C in three commits. Nothing from M2+ exists (no org structure, agents,
  tasks, approvals, map, documents, commerce or backup).
- Not done: final check on port 8000 (blocked by the `api-gateway` container); owner's own
  click-through of wizard / login / logout / restart persistence.
