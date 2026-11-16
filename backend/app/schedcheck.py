"""Is the scheduler in order? Used by `./village doctor`.

Usage: python -m app.schedcheck     prints "STATUS<TAB>message"

Checks that APScheduler is installed, that the database has the schedule tables, and — when the
Village is running — asks its /api/health whether the scheduler thread is alive. Nothing is
started or changed.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request


def _health(base_url: str) -> dict[str, object] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base_url + "/api/health", timeout=2) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001  (not running, or not the Village)
        return None


def check() -> tuple[str, str]:
    try:
        import apscheduler
    except ImportError:
        return "FAIL", "scheduler: APScheduler is not installed (run ./village setup)"
    from app.config import get_settings

    settings = get_settings()
    version = getattr(apscheduler, "version", None) or getattr(apscheduler, "__version__", "?")
    if not settings.db_file.exists():
        return "FAIL", "scheduler: database not created yet (run ./village setup)"
    try:
        with sqlite3.connect(f"file:{settings.db_file}?mode=ro", uri=True) as connection:
            total, paused = connection.execute("SELECT COUNT(*), COALESCE(SUM(paused), 0) FROM schedule").fetchone()
            timezone = (connection.execute("SELECT timezone FROM village LIMIT 1").fetchone() or ("Asia/Dhaka",))[0]
    except sqlite3.Error:
        return "FAIL", "scheduler: the database has no schedule tables (run ./village setup)"
    schedules = f"{total} schedule(s), {paused} paused" if total else "the built-in schedules are added at the first start"
    health = _health(f"http://{settings.host}:{settings.port}")
    if health is None or "scheduler" not in health:
        if not settings.scheduler:
            return "WARN", "scheduler: switched off (VILLAGE_SCHEDULER=0) — no schedule will run"
        return "PASS", f"scheduler: APScheduler {version} installed; it starts with the Village ({schedules})"
    if health["scheduler"] == "running":
        return "PASS", f"scheduler: running inside the Village — {health.get('scheduler_jobs', '?')} job(s), {schedules}, timezone {timezone}"
    if not settings.scheduler:
        return "WARN", "scheduler: switched off (VILLAGE_SCHEDULER=0) — no schedule runs"
    return "FAIL", "scheduler: the Village is running but its scheduler is not (see ./village logs)"


if __name__ == "__main__":
    status, message = check()
    print(f"{status}\t{message}")
