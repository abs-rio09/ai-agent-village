# PROGRESS

Milestone in progress: **M1 — Foundation** (Part A done; Parts B and C pending).

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

## In progress
- M1 Part B — admin auth + first-run wizard API.
- M1 Part C — React shell + wizard UI served by FastAPI.

## Broken & known issues
- **Port 8000 is occupied on this PC** by the Docker container `api-gateway` (0.0.0.0:8000), which
  belongs to another project. `./village start` on the default port fails until that container is
  stopped; `./village doctor` reports it as a FAIL. Workaround: `VILLAGE_PORT=<other>`.
- `VILLAGE_SECRET_KEY` is required and generated, but nothing uses it yet (session tokens are
  random and stored hashed). It is reserved for future signing needs.
- shellcheck is not installed, so the CLI was only checked with `bash -n`
  (`sudo apt install shellcheck` to enable that test).
- Starlette prints a deprecation warning that its TestClient will prefer `httpx2` over `httpx`;
  harmless today.

## Last session
- Built M1 Part A. Nothing from M2+ exists.
