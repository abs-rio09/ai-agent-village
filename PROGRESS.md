# PROGRESS

Milestone **M1 — Foundation**: built, committed and **accepted by the owner**. The owner verified
it himself on the default port 8000 (wizard, dashboard, restart persistence, logout/login).

Milestone **M2 — Organization**: Part A (backend) is built and committed. Part B (frontend) is
not built yet — the three Administration pages still say "Coming in M2".

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
  `status` all passed with `VILLAGE_DB_PATH=/tmp/village-m1.db` on port 8010
  (`VILLAGE_PORT=8010`).
- Acceptance on port 8000: done by the owner (wizard, dashboard, restart persistence,
  logout/login) after the `api-gateway` Docker container that held the port was stopped and its
  auto-restart disabled.

### M2 Part A — organization backend
- Migration `0003`: `upazila_template`, `union_template`, `ward_template`, `upazila`,
  `union_unit` ("union" is an SQL keyword), `ward`, `office`. Every foreign key down the
  hierarchy is `ON DELETE CASCADE`; all tables have `created_at`/`updated_at`. `office` has a
  CHECK (`ward` needs a ward, `central` must not have one) and a partial unique index that allows
  only one central office. `app_meta.schema_version` = 3.
- Seeded in the migration: the 6 Upazila templates (SPEC §5) with 5 Union names each (SPEC §11),
  a ward set per template, and the one Central Administration office. Study uses the 9 ward
  responsibilities from SPEC §11 (as both ward name and responsibility). No Upazila, Union or Ward
  is seeded: structure is generated on demand only, never at setup.
- **[owner to supply ward names for Business/Career/Research/Project/Personal]** — the SPEC has
  no ward list for these five templates, so they are seeded as "Ward 1".."Ward 9" with an empty
  responsibility. They can be filled in from the Templates editor (Part B) without code.
- Templates are editable without code: `GET /api/templates`, `PATCH /api/templates/{key}`,
  `PATCH /api/templates/unions/{id}`, `PATCH /api/templates/wards/{id}`. Edits affect future
  generation only (existing units are copies).
- CRUD: `/api/upazilas`, `/api/upazilas/{id}`, `/api/upazilas/{id}/unions`, `/api/unions/{id}`,
  `/api/unions/{id}/wards` (POST adds the next ward number and its office), `/api/wards/{id}`,
  `/api/offices/{id}`, `GET /api/offices/central`. Names are trimmed, 1–80 characters; duplicate
  name → 409; missing parent → 404. Edits use `PATCH`.
- Deletes cascade and need the body `{"confirm_name": "<exact name>"}` (otherwise 400). A
  `TODO(M3)` comment marks where deleting units that still have agents must be blocked.
- `POST /api/upazilas/standard` (one Upazila per template, skips existing names),
  `POST /api/upazilas/{id}/generate-standard` (missing template Unions + their wards + one office
  per ward, in one transaction; second run creates 0) and `GET .../generate-standard/preview`
  (same counts, no writes). 400 when the Upazila has no template. Counts come from the template
  rows; nothing is hardcoded.
- `GET /api/org/tree` (nested tree with counts, 5 queries whatever the size) and
  `GET /api/stats/overview` (real counts: upazilas, unions, wards, offices, ward_offices — no
  agent or task numbers).
- Choices made that the brief left open:
  - A ward added by hand also gets its office (there is no "create office" endpoint, and the
    Ward & Office page needs every ward to have one). Office name = "<ward name> Office".
  - Renaming a ward also renames its office while the office still has that automatic name; an
    office renamed by hand is left alone.
  - `offices` in the stats counts every office row, so it includes Central Administration
    (Study generated → 46); `ward_offices` is the number without it (45).
  - Template descriptions are seeded empty (the SPEC gives none).
- Tests: pytest 121 passed, 1 skipped (shellcheck). New in `tests/test_m2_org.py` (39 tests): seed
  names vs SPEC, CRUD, 409/404/422, delete confirmation and cascades, generation (5/45/45, wards
  1..9, idempotent, one transaction — a forced failure midway leaves nothing), edited templates used
  by the next generation only, stats vs DB, tree counts, no query-per-node, 401 on every new route,
  upgrade 0002→0003 keeps data, models match migrations, parallel requests do not duplicate.
- Not yet done for Part A: no run against a real server process or a copy of the real database
  (that is the M2 final check, after Part B).

## In progress
- M2 Part B (frontend): not started.

## Broken & known issues
- `VILLAGE_SECRET_KEY` is required and generated, but nothing uses it yet (session tokens are
  random and stored hashed). It is reserved for future signing needs.
- Demo/AI: no AI provider code exists yet. `ai_mode`, the Ollama URL and the Anthropic key are
  only stored; **neither Ollama nor Anthropic has been contacted or tested**.
- `GET /api/health` `demo_mode` follows the brief literally ("no Anthropic key set"), so a village
  in Ollama mode without a key still reports `demo_mode: true`.
- Login lockout is in memory: it resets when the server restarts. Sessions are not cleaned up
  on a schedule (expired rows are deleted at the next login).
- Org names are compared exactly: "Garden" and "garden" count as two different names.
- A session model/migration mismatch from M1 was fixed in the model only (`session.user_id` now
  declares the index that migration 0002 already created); no schema change.
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
- Recorded M1 as accepted by the owner on port 8000.
- Built and committed M2 Part A (backend). Nothing from M3+ exists (no agents, tasks, approvals,
  map, documents, commerce or backup).
- Next: M2 Part B (frontend), then the M2 final check on a temp DB and a copy of the real DB.
