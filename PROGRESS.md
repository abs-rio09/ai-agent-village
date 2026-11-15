# PROGRESS

Milestone **M1 — Foundation**: built, committed and **accepted by the owner**. The owner verified
it himself on the default port 8000 (wizard, dashboard, restart persistence, logout/login).

Milestone **M2 — Organization**: Parts A (backend) and B (frontend) are built and committed and
passed the final check on a temp database and port 8012. **Not yet accepted by the owner.** The
live village on port 8000 was rebuilt and restarted by the owner on 2026-11-12 (seen only from the
new process and the `frontend/dist` timestamp; the assistant did not inspect it). The owner's
confirmation of M2 has not been recorded (see "How to verify M2 on the live village").

**DEV-DOCS-01 — README, screenshots, license, CI**: done and committed. No application code,
migration or test was changed. The CI workflow has **not run on GitHub yet** (nothing was pushed).

**DEV-M2-FIX-01 — max 9 wards per Union**: done and committed (see "M2 fix: max 9 wards").

Milestone **M3 — Agents & Tasks**: in progress. Parts A (agent registry backend) and B (tasks,
routing, delegation backend) are built and committed; Part C (the pages) is not built yet. See
the M3 sections below for what exists.

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

### M2 Part B — organization frontend
- The three "Coming in M2" pages are real now (`frontend/src/pages/Upazilas.tsx`, `Unions.tsx`,
  `Wards.tsx`, `TemplatesPanel.tsx`; shared pieces in `components/org.tsx`, `Dialog.tsx`,
  `OrgTreeView.tsx`). All data comes from `/api/org/tree`, `/api/templates` and the CRUD endpoints.
- **Upazila Management**: cards (name, icon, template, union/ward/office counts), create/edit/delete,
  "Create the N standard Upazilas" (shown only while none exist; N = number of templates, not a
  hardcoded 6), and "Generate Standard Structure" on every Upazila that has a template. Generate
  opens a dialog with the preview counts → Confirm → the counts the server really created.
  Three tabs: Upazilas, Tree view, Templates.
- **Union Management**: pick an Upazila → its Unions with ward/office counts; create/edit/delete.
- **Ward & Office Management**: pick an Upazila and Union → grid of wards (number, name,
  responsibility, office name); inline edit of ward name, responsibility and office name;
  "Add ward" (next number, opens in edit mode); delete; plus a panel to rename the Central
  Administration office.
- **Templates** tab: edit a template's name, its Union names and its ward names/responsibilities.
  Only changed fields are sent. A note says the change applies to future generation only.
- Breadcrumbs (Village › Upazila › Union › Ward) on all three pages, and a collapsible tree view
  (nested lists, buttons with `aria-expanded`, Expand all / Collapse all) whose nodes link to the
  page that manages them. It lives in the "Tree view" tab of Upazila Management until the map (M5).
- Every delete uses a dialog where the exact name must be typed; the dialog says what goes with it
  ("5 Unions, 45 Wards and 45 Offices"). Server errors (409 duplicate name, etc.) are shown in the
  dialog or page.
- Overview: four real counts from `/api/stats/overview` (Upazilas, Unions, Wards, Offices). No
  numbers at all for agents or tasks; the text says they arrive in M3/M4.
- Sidebar: the three Administration pages no longer carry an "M2" badge (`BUILT_MILESTONE = 2` in
  `nav.ts`).
- Bug found and fixed during the browser check: dialogs were rendered inside the animated page
  wrapper, whose CSS transform confined the "fixed" backdrop to the page area and left the panel
  see-through. Dialogs are now rendered in a portal on `<body>` with an opaque panel (regression
  test added).
- Tests: Vitest + RTL 51 passed (20 new in `src/test/org.test.tsx`, 3 new in `app.test.tsx`):
  create-Upazila validation, 409 shown, standard-Upazilas button, generate preview → result,
  delete blocked until the typed name matches, tree expand/collapse, breadcrumbs, union and ward
  CRUD, inline edit sends only what changed, template save, overview counts. pytest 121 passed,
  1 skipped (shellcheck). `tsc --noEmit` and `vite build` succeed.

### M2 final check (run by the assistant, 2026-11-12)
- Never touched `data/village.db`, `data/.env`, `frontend/dist` or port 8000 (the owner's live
  village kept running the whole time; its PID and the DB file's modification time are unchanged).
- Upgrade on real data: a read-only copy of `data/village.db` was upgraded 0002 → 0003. The
  `village`, `admin_user` and `session` rows are byte-identical before and after (same content
  hash); 6 templates, 30 union templates, 54 ward templates and 1 central office were added;
  `integrity_check` and `foreign_key_check` are ok.
- Real server on `VILLAGE_DB_PATH=/tmp/village-m2.db VILLAGE_PORT=8012` with a scratch `.env` and a
  scratch frontend build. With curl: every new route 401 without a session; setup creates no
  structure; `/upazilas/standard` creates 6 then 0; generate on Study previews and creates
  5/45/45, then 0 (skipped 5); wards 1..9 with the SPEC names; duplicate name 409; delete without
  or with a wrong name 400, with the exact name 200 and cascading; cross-origin write 403.
- Real (headless) browser on that server: login → empty state → "Create the 6 standard
  Upazilas" → generate Study (preview 5/45/45 → result 5/45/45 → second run "Nothing to create")
  → tree expand → breadcrumbs → create/rename/delete an Upazila, Unions and Wards → inline ward
  and office edit → central office rename → template edit used by the next generation (and Study,
  generated earlier, unchanged) → cascade delete of Study → Overview counts equal to the API.
  Data survived a server restart. No tracebacks in the server log.
- Deviations from the brief's wording, on purpose:
  - The temp server was started with `python -m app.main`, not `./village start`: the CLI has one
    PID file (`run/village.pid`) and it belongs to the live village.
  - `npm run build` itself was not run, because it would have replaced `frontend/dist` under the
    running live server. Its two steps were run instead (`tsc --noEmit`, then `vite build` into
    a scratch folder). `./village setup` does the real build.

### DEV-DOCS-01 — README, screenshots, license, CI (2026-11-12, no app changes)
- `README.md` (GitHub-flavoured, 246 lines): tagline, badges (no CI badge), hero screenshot, status
  table M1–M9, working features (M1 + M2 only), screenshot grid, Mermaid architecture diagram,
  tech stack, quick start, `./village` command table, security, testing, structure, roadmap,
  how it was built, author, license. Every image and link target exists; the Mermaid block was
  parsed and rendered with Mermaid 11.4.1 in a headless browser (GitHub's own renderer was not
  tested).
- `LICENSE`: MIT, copyright 2026 Abu Bakkar Siddik.
- `docs/screenshots/` — five real 1440×900 screenshots (175–260 KB each): `overview.png`,
  `setup-wizard.png`, `upazila-management.png`, `generate-structure.png`, `tree-view.png`. Taken
  in a headless browser against a server on port 8013 with `VILLAGE_DB_PATH=/tmp/village-shots.db`,
  a scratch `.env` and a scratch frontend build. The village was created through the real wizard
  ("Demo Village", "Demo Chairman", user "demo"), then the standard Upazilas and the Study
  structure were generated through the UI. The temp database was deleted afterwards.
- `.github/workflows/ci.yml` — on push and pull request, `ubuntu-latest`, no secrets:
  backend (Python 3.12: `pip install -r backend/requirements.txt`, `pytest`), frontend (Node 22:
  `npm ci`, `npm test`, `npm run build`) and a build-only job on Node 20.
- Local dry run of exactly those commands in a clean export of the commit, with interpreters
  downloaded into a scratch folder (nothing installed system-wide):
  - Python 3.12.16: pytest **121 passed, 1 skipped** without shellcheck; **122 passed** with
    shellcheck 0.11.0 on the PATH (GitHub's runner has shellcheck, so the test will run there).
  - Node 22.23.5: `npm ci`, Vitest **51 passed**, `npm run build` ok.
  - Node 20.20.2: `npm ci` (engine warnings) and `npm run build` ok; **`npm test` fails**
    (see "Broken & known issues").
- `.gitignore`: added `.env`, `.env.*`, `data/.env*` (the temp files written while a key is being
  saved were not covered), `*.log`, `*.pid`, `coverage/`, `.coverage`, `.playwright-mcp/`,
  `.DS_Store`. `git ls-files | grep -E '\.env|\.db|\.log|\.pid'` prints nothing.
- Secret scan of tracked files: no real keys, no email addresses, no `/home/...` paths, no phone
  numbers. Hits that are intentional: fake `sk-ant-...TESTKEY...` strings and test passwords in the
  test files; the PC's CPU model in `CLAUDE.md` and `docs/SPEC.md`. Commits are authored with a
  GitHub no-reply address.
- Milestone plan used in the README: M1–M8 as already recorded here, plus **M9 = background
  automation (scheduler, persistent queue, restart recovery) and release hardening**. M9 is the
  assistant's assumption — the brief asked for M1–M9 but nothing in the repo defined M9. It is
  the part of the SPEC (§9) that M3–M8 did not cover.

### M2 fix: max 9 wards (DEV-M2-FIX-01, 2026-11-15)
- One constant, `MAX_WARDS_PER_UNION = 9`, in the new `backend/app/limits.py`. Every other place
  reads it; the frontend gets it from the API (`max_wards_per_union` in `GET /api/org/tree`,
  `max_wards` on every template in `GET /api/templates`) and never hard-codes 9.
- `POST /api/unions/{id}/wards` on a Union that already has 9 wards → **409** "A Union can have at
  most 9 wards. Delete a ward before adding another." The count (not the highest number) is
  limited, so after a delete the next ward is allowed again (it still gets the next number, e.g. 10).
  The check runs after the existing write lock on the Union, so parallel adds cannot pass it twice.
- Generation reads at most 9 ward rows per template (`LIMIT`), so a generated Union never gets more
  than 9 — tested with a 10th template row inserted directly into the database.
- New endpoint `PUT /api/templates/{key}/wards` `{"wards": [{name, responsibility}, …]}`: saves a
  template's whole default ward set (1–9 names; 10 or more, or none → **422**). Rows keep their id
  where the number stays; extra rows are added, missing ones removed. Only the template changes.
  It is session-protected (added to the route list in `test_every_m2_route_needs_a_session`).
  This endpoint is new: before, templates could only rename their 9 seeded wards, so "reject a
  template with more than 9 names on save" needed a way to save a ward set.
- Ward & Office Management: at 9 wards the "Add ward" button is replaced by the note "Maximum 9
  wards per Union"; with 8 or fewer the button is shown.
- Templates tab: each default ward row has a remove button (disabled for the last one), and an
  "Add ward name" button that is replaced by the same note at 9 rows. Plain renames still use the
  old per-ward `PATCH`; adding/removing rows saves the whole set with the new `PUT`.
- No migration, no change to existing data. A Union that already had more than 9 wards keeps them;
  it just cannot get more (the button is hidden and the API answers 409).
- Tests: pytest **128 passed, 1 skipped** (shellcheck not installed); 7 new tests in
  `backend/tests/test_m2_fix_max_wards.py`. Vitest **56 passed** (5 new; the existing "adds the
  next ward" test now starts from a Union with 8 wards, because 9 hides the button). `npm run
  build` ok, `bash -n village` ok. The Vitest run used Node 24.21.0.
- Checked on a real server (scratch DB + `.env`, port 8011, now stopped and the files only in the
  scratchpad): generate Study → 10th ward 409, tree reports 9, `PUT` with 10 names 422; the Ward
  page showed the note instead of the button (screenshot checked, then deleted). The Templates tab
  was **not** checked in a browser, only in Vitest.
- **The live village on port 8000 still runs the old code** — it was not restarted or rebuilt by
  the assistant. Run `./village stop && ./village setup && ./village start` to use the fix.

### M3 Part A — agent registry, templates, Demo provider (backend, 2026-11-15)
- Migration `0004_agents.py` (schema_version 4): `agent_template` and `agent`. An agent stores only
  `office_id`; its Upazila/Union/Ward are derived from the office in the API (`location`, `path`).
  One column beyond the brief's list: `agent.is_central_manager` with a partial unique index, so the
  database itself allows at most one Central Manager (same idea as the single central office).
- Seed (`backend/app/seed.py`, data in `backend/app/agent_catalog.py`): the 15 templates of SPEC §6
  and ONE "Central Manager" (Village Manager template) in Central Administration. It runs in
  migration 0004 and again at every app start (only if the `agent` table exists); it only inserts
  what is missing, never changes existing rows. The Doctor template says general information and
  wellness only, no diagnosis, no prescription; the Repair Technician template says approved tools
  only, no terminal access — and the tool catalogue has no shell/terminal/filesystem tool at all.
- Tools (10 keys, SPEC §8E) and permissions (9 keys, 4 marked sensitive) are a fixed catalogue in
  `agent_catalog.py`, served by `GET /api/agent-options` (an extra endpoint, needed for form
  labels). **They are stored on the agent but NOT enforced, and no tool is executable** — that is
  M4. `memory_config` and `working_schedule` are stored as `{}` and are read-only for now.
- API (session required): `GET /api/agent-templates`, `GET /api/agent-options`, `GET /api/agents`
  (`office_id`, `upazila_id`, `lifecycle` filters; one query), `POST /api/agents` (`template_id`,
  `display_name`, `office_id`; template defaults copied, optional overrides, `activate` default
  true), `GET/PATCH /api/agents/{id}`, `POST /api/agents/{id}/activate|pause|disable`,
  `DELETE /api/agents/{id}` (needs `{"confirm_name"}` like the org deletes).
- Central Manager: pause, disable, delete and moving it to another office → 409. It can be renamed.
- Deleting a Ward/Union/Upazila: the agents of the deleted offices are kept, get `office_id` NULL
  and are disabled (`agents_disabled` in the delete response). This replaces the `TODO(M3)` notes
  in `org.py` that planned a 409 instead. An agent without an office cannot be activated (409)
  until it is given a new office.
- Delete rule: in Part A no agent could have history yet; Part B made the "has history → 409,
  disable instead" rule real and tested it.
- Providers: `backend/app/providers/base.py` (`Provider`: `name`, `is_configured()`,
  `reply(agent, task) -> str`), `providers/demo.py` (fixed three-step outline per template, every
  reply starts with "[Demo]" and says no AI model was used; no network) and a registry that returns
  Demo for any unknown or unconfigured provider. **Only Demo exists**: an agent's `provider` can
  only be "demo"; Ollama and Anthropic are not implemented and were not contacted.
- `GET /api/stats/overview` now also returns `agents` and `active_agents`.
- Three M2 tests were adjusted because they pinned M2-only facts: "head is 0003" (now upgrades to
  0003 explicitly), "stats have no agent numbers" and "no routes other than M1/M2".
- Tests: pytest **165 passed, 1 skipped** (shellcheck); 37 new in `tests/test_m3_agents.py`
  (0003→0004→0003→0004 on a database with real M2 rows, seeding three times, CRUD, filters,
  lifecycle, Central Manager protection, office deletion at ward/union/upazila level, Demo
  provider with sockets blocked, 401 on all 10 routes). No frontend change in this part.

### M3 Part B — tasks, Central Manager routing, delegation (backend, 2026-11-15)
- Migration `0005_tasks.py` (schema_version 5): `task` (every SPEC §8B field, plus `depth` and
  `updated_at`) and `agent_message` (SPEC §8C). Nothing is seeded. CHECK constraints on status,
  priority (`low|normal|high`) and message type (`delegation|result`).
- Status rules: `backend/app/task_status.py` holds the 7 statuses and the one transition table.
  Every status change in the app goes through `task_runner.move_task`, which checks that table
  and only changes a task that still has the status the caller saw (so a cancel and the worker
  cannot overwrite each other). `WAITING_APPROVAL` exists in the table but nothing uses it (M4).
- Task runner (`backend/app/task_runner.py`): ONE daemon thread, started and stopped by the
  FastAPI lifespan, polling SQLite every 0.5 s, one step at a time (route a request / let an agent
  answer / collect the children into a report). `VILLAGE_TASK_WORKER=0` switches it off (the
  tests do that and run the queue themselves). On start, tasks left RUNNING go back to QUEUED with
  "Interrupted by a restart of the village; queued again." in `error`, and a re-queued request
  that already has child tasks is not delegated a second time. Runtime state: an agent is
  `working` while its task runs and `idle` after; the Central Manager is `waiting` while it waits
  for child tasks.
- Central Manager (`backend/app/central_manager.py`, keyword table in
  `backend/app/routing_keywords.py`): the request text is matched against the keywords of each
  Upazila's template plus the words of the Upazila's own name (Upazilas without a template: their
  name and Union names). Most hits wins. Then the ACTIVE agent of that Upazila whose role,
  description, Ward and Union share the most words with the request gets a child task (else the
  first active one). When the children are done the parent gets a report that starts with
  "[Demo] Central Manager report". No Upazila matched / no active agent → the parent is FAILED
  with a readable reason. The Central Manager never calls a provider for itself. Delegation depth
  is limited to 3; M3's own flow only ever uses depth 1 (the deeper levels are tested by calling
  `delegate` directly). **This is keyword matching, not understanding** — a request with no
  keyword fails, and a request with misleading words goes to the wrong Upazila.
- API (session required): `POST /api/tasks` (`title`, optional `description`, `priority`),
  `GET /api/tasks` (`status`, `agent_id`, `top_level`, `limit`), `GET /api/tasks/{id}` (children
  + messages of the whole tree), `POST /api/tasks/{id}/cancel` (cancels unfinished children too;
  409 when already finished).
- Agents: an agent with any task or message has `has_history: true` and its delete answers 409
  "…Disable it instead — its history is kept."
- Tests: pytest **259 passed, 1 skipped** (shellcheck); 94 new in `tests/test_m3_tasks.py`
  (49 of them are the transition table): 0003→0004→0005→0004→0003→head on a database with real
  rows, routing per Upazila (pure and through the API), failure reasons, paused/disabled agents,
  provider failure, depth limit, cancel (also while the agent is working), crash recovery, the
  real worker thread inside the app, priority, history, 401 on all 4 routes.
- Checked on a real server (scratch DB + `.env`, port 8013, started with `python -m app.main`,
  now stopped): Study structure generated, Study Assistant "Mina" created in Ward 1, "help me
  prepare for my exam" → child SUCCEEDED with a "[Demo]" reply → parent SUCCEEDED with the report,
  two messages; "hello there" → FAILED with the reason. No error in the server log.
- Not done / limits: one agent per request (no multi-agent coordination); no retry of failed
  tasks; no task deletion or clean-up of old tasks; providers other than Demo do not exist.

## How to verify M2 on the live village
`./village stop && ./village setup && ./village start`, log in, then:
1. Village Overview: Upazilas 0, Unions 0, Wards 0, Offices 1 (Central Administration).
2. Upazila Management → "Create the 6 standard Upazilas" → six cards.
3. Study Upazila card → "Generate Standard Structure" → preview 5 / 45 / 45 → Confirm → Created
   5 / 45 / 45 → Done. Click it again: "Nothing to create".
4. Tab "Tree view" → expand Study Upazila → expand a Union → 9 wards, Class Routine … Daily
   Academic Reporting.
5. Union Management (pick Study Upazila): New Union, edit it, delete it (type its name).
6. Ward & Office Management (pick a Union): edit a ward inline. With 9 wards there is no
   "Add ward" button, only "Maximum 9 wards per Union"; delete a ward → the button comes back.
7. Tab "Templates" → Business Upazila → fill in ward names → Save → generate Business.
8. Overview again: the four counts match.

## In progress
- Nothing. M3 has not been started.

## Broken & known issues
- `VILLAGE_SECRET_KEY` is required and generated, but nothing uses it yet (session tokens are
  random and stored hashed). It is reserved for future signing needs.
- Demo/AI: no AI provider code exists yet. `ai_mode`, the Ollama URL and the Anthropic key are
  only stored; **neither Ollama nor Anthropic has been contacted or tested**.
- `GET /api/health` `demo_mode` follows the brief literally ("no Anthropic key set"), so a village
  in Ollama mode without a key still reports `demo_mode: true`.
- Login lockout is in memory: it resets when the server restarts. Sessions are not cleaned up
  on a schedule (expired rows are deleted at the next login).
- M2 has not been confirmed by the owner on the live village yet (see above).
- **Node 20 cannot run the frontend tests.** Vitest 5.1 and jsdom 31 declare Node >= 22.12 /
  22.22 and their workers crash on Node 20.20 (`undici` fails to load). The build still works on
  Node 20, and react-router 8.5 also declares Node >= 22.22 (warning only). So CI tests on Node 22
  and only builds on Node 20 — a deviation from the brief ("Node 20"). `frontend/package.json`
  still says `engines.node >= 20.19` and CLAUDE.md says "Node >= 20"; neither was changed.
  **Owner decision needed:** raise the minimum to Node 22, or pin Vitest/jsdom to versions that
  support Node 20.
- The CI workflow has never run on GitHub. Not verified there: the runner's own shellcheck
  version against `village` (0.11.0 passes locally), and npm 10 with Node 20 (npm 11 was used
  locally). The README has no CI badge until the first green run.
- Study wards show the same text twice (name and responsibility), because the SPEC gives one
  label per ward and both fields were seeded with it. Edit either in the Templates tab.
- Templates: default wards can be added/removed (1–9, DEV-M2-FIX-01), but Unions still cannot
  be added to or removed from a template.
- Wards cannot be renumbered or reordered; deleting a ward leaves a gap in the numbers. Upazilas
  and Unions have a `sort_order` in the API but no reorder control in the UI.
- Deleting an Upazila/Union/Ward is not blocked by agents: the agents of the deleted offices
  are kept, lose their office and are disabled (M3 Part A).
- The org pages load the whole tree (`/api/org/tree`) and reload it after every change. Fine for
  the standard structure (6 Upazilas → 270 wards was measured at 5 queries); not paginated.
- Org names are compared exactly: "Garden" and "garden" count as two different names.
- A session model/migration mismatch from M1 was fixed in the model only (`session.user_id` now
  declares the index that migration 0002 already created); no schema change.
- The "Coming in M<n>" numbers (M2 org structure, M3 agents + AI settings, M4 tasks/approvals/
  communication, M5 map, M6 memory + documents, M7 commerce + integrations, M8 reports, settings,
  backup, health) are an assumption — only "backup = M8" was given. They live in
  `frontend/src/nav.ts`. M9 (automation + release hardening) is an assumption too and exists only
  in the README.
- The small-screen layout was only spot-checked: the Ward page at 420 px wide has no horizontal
  overflow. The other pages and the drawer were checked at desktop width only.
- `./village setup` runs `npm ci` every time, as specified, so each run reinstalls
  `node_modules` (a few seconds here).
- shellcheck is not installed on this PC, so the everyday test run skips that test
  (`sudo apt install shellcheck` to enable it). It was run once with shellcheck 0.11.0 from a
  scratch install during DEV-DOCS-01 and `village` passed.
- Starlette prints a deprecation warning that its TestClient will prefer `httpx2` over `httpx`;
  harmless today.

## Last session
- DEV-M2-FIX-01: a Union may hold at most 9 wards (API 409, generation capped, template ward set
  1–9 with 422 above, UI hides "Add ward" at 9 and shows a note). Tests pass; one commit; nothing
  pushed; the live village was not restarted.
- Still waiting for: the owner's confirmation of M2, the ward names for the
  Business/Career/Research/Project/Personal templates, the Node 20 vs 22 decision, and the first
  CI run on GitHub (then the CI badge can be added).
