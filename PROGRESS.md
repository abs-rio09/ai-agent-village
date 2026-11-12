# PROGRESS

Milestone **M1 — Foundation**: built, committed and **accepted by the owner**. The owner verified
it himself on the default port 8000 (wizard, dashboard, restart persistence, logout/login).

Milestone **M2 — Organization**: Parts A (backend) and B (frontend) are built and committed and
passed the final check on a temp database and port 8012. **Not yet accepted by the owner**: the
live village on port 8000 still runs the M1 code until `./village stop && ./village setup &&
./village start` is run (see "How to verify M2 on the live village").

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

## How to verify M2 on the live village
`./village stop && ./village setup && ./village start`, log in, then:
1. Village Overview: Upazilas 0, Unions 0, Wards 0, Offices 1 (Central Administration).
2. Upazila Management → "Create the 6 standard Upazilas" → six cards.
3. Study Upazila card → "Generate Standard Structure" → preview 5 / 45 / 45 → Confirm → Created
   5 / 45 / 45 → Done. Click it again: "Nothing to create".
4. Tab "Tree view" → expand Study Upazila → expand a Union → 9 wards, Class Routine … Daily
   Academic Reporting.
5. Union Management (pick Study Upazila): New Union, edit it, delete it (type its name).
6. Ward & Office Management (pick a Union): edit a ward inline, "Add ward", delete a ward.
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
- M2 has not been clicked through by the owner on the live village yet (see above).
- Study wards show the same text twice (name and responsibility), because the SPEC gives one
  label per ward and both fields were seeded with it. Edit either in the Templates tab.
- Templates: names can be edited, but Unions/wards cannot be added to or removed from a template
  yet (the brief asked for editing only). Changing how many Unions or wards a template has needs
  a new migration or a future feature.
- Wards cannot be renumbered or reordered; deleting a ward leaves a gap in the numbers. Upazilas
  and Unions have a `sort_order` in the API but no reorder control in the UI.
- Deleting an Upazila/Union/Ward is not blocked by agents because agents do not exist yet;
  `TODO(M3)` comments in `backend/app/api/org.py` mark where that check must go.
- The org pages load the whole tree (`/api/org/tree`) and reload it after every change. Fine for
  the standard structure (6 Upazilas → 270 wards was measured at 5 queries); not paginated.
- Org names are compared exactly: "Garden" and "garden" count as two different names.
- A session model/migration mismatch from M1 was fixed in the model only (`session.user_id` now
  declares the index that migration 0002 already created); no schema change.
- The "Coming in M<n>" numbers (M2 org structure, M3 agents + AI settings, M4 tasks/approvals/
  communication, M5 map, M6 memory + documents, M7 commerce + integrations, M8 reports, settings,
  backup, health) are an assumption — only "backup = M8" was given. They live in
  `frontend/src/nav.ts`.
- The small-screen layout was only spot-checked: the Ward page at 420 px wide has no horizontal
  overflow. The other pages and the drawer were checked at desktop width only.
- `./village setup` runs `npm ci` every time, as specified, so each run reinstalls
  `node_modules` (a few seconds here).
- shellcheck is not installed, so the CLI was only checked with `bash -n`
  (`sudo apt install shellcheck` to enable that test).
- Starlette prints a deprecation warning that its TestClient will prefer `httpx2` over `httpx`;
  harmless today.

## Last session
- Recorded M1 as accepted by the owner on port 8000.
- Built M2 in two commits: Part A (backend) and Part B (frontend), then ran the final check on a
  temp database, a copy of the real database and a real browser (details above).
- Nothing from M3+ exists (no agents, tasks, approvals, map, documents, commerce or backup).
- Waiting for: the owner's click-through of M2 on the live village, and the ward names for the
  Business/Career/Research/Project/Personal templates.
