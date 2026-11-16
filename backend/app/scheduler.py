"""Schedules: APScheduler inside the FastAPI process (docs/SPEC.md §9).

A schedule NEVER does work. When it is due it creates ONE task in the queue, and the task
runner (app/task_runner.py) does the rest — the same queue, the same permission checks, the
same audit log as a request typed by the Chairman.

  • The schedules are rows of the `schedule` table (two built-in ones + the owner's).
  • APScheduler only keeps time: one job per row ("schedule:<id>"), stored in the same SQLite
    database (table apscheduler_jobs), timezone of the village (Asia/Dhaka by default),
    coalesce on, at most one instance per job.
  • Idempotency: a run is identified by "<schedule id>:<the time it was scheduled for>". That
    key is UNIQUE in `schedule_run`, so one scheduled run creates at most one task — also when
    the job fires twice, or again after a restart. After downtime the missed runs of a
    schedule are folded into one (coalesce).

Built-in schedules: "Agent health check" (every 10 minutes) and "Daily report" (21:00).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_engine, get_session_factory, utcnow
from app.models import Agent, Schedule, ScheduleRun, Task, Village
from app.task_status import ACTIVE, ASSIGNED, QUEUED

log = logging.getLogger("village.scheduler")

DEFAULT_TIMEZONE = "Asia/Dhaka"
HEALTH_CHECK = "health_check"
DAILY_REPORT = "daily_report"
# key → (name, what it does, trigger_type, interval_minutes, daily_time)
BUILTIN_SCHEDULES: dict[str, tuple[str, str, str, int | None, str | None]] = {
    HEALTH_CHECK: (
        "Agent health check",
        "Marks tasks that have been RUNNING without progress for too long as FAILED.",
        "interval",
        10,
        None,
    ),
    DAILY_REPORT: (
        "Daily report",
        "Creates the daily summary task: what was done, what failed and what waits for you.",
        "daily",
        None,
        "21:00",
    ),
}
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 7 * 24 * 60
MAX_CUSTOM_SCHEDULES = 50
# A job never fires before its time, but clocks are stored as floats: allow a second of slack
# when working out which scheduled run a firing belongs to.
_SLACK = timedelta(seconds=1)


# ---------------------------------------------------------------- time


def village_timezone(db: Session) -> ZoneInfo:
    """The timezone chosen in the setup wizard; Asia/Dhaka when there is none or it is unknown."""
    name = db.execute(select(Village.timezone).limit(1)).scalar_one_or_none() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def scheduled_time(schedule: Schedule, now: datetime, tz: ZoneInfo) -> datetime:
    """The scheduled time (naive UTC) of the run that a firing at `now` belongs to: the latest
    run time that is not after `now`."""
    if schedule.trigger_type == "interval":
        step = timedelta(minutes=schedule.interval_minutes or 1)
        steps = max(0, (now + _SLACK - schedule.anchor_at) // step)
        return schedule.anchor_at + steps * step
    hour, minute = _clock(schedule.daily_time or "00:00")
    local = (now + _SLACK).replace(tzinfo=UTC).astimezone(tz)
    run = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run > local:
        run -= timedelta(days=1)
    return run.astimezone(UTC).replace(tzinfo=None)


def next_run_time(schedule: Schedule, now: datetime, tz: ZoneInfo) -> datetime | None:
    """When the schedule runs next (naive UTC); None while it is paused."""
    if schedule.paused:
        return None
    if schedule.trigger_type == "interval":
        step = timedelta(minutes=schedule.interval_minutes or 1)
        if now < schedule.anchor_at:
            return schedule.anchor_at
        return schedule.anchor_at + ((now - schedule.anchor_at) // step + 1) * step
    hour, minute = _clock(schedule.daily_time or "00:00")
    local = now.replace(tzinfo=UTC).astimezone(tz)
    run = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run <= local:
        run += timedelta(days=1)
    return run.astimezone(UTC).replace(tzinfo=None)


def describe_trigger(schedule: Schedule) -> str:
    if schedule.trigger_type == "daily":
        return f"every day at {schedule.daily_time}"
    minutes = schedule.interval_minutes or 1
    if minutes % 1440 == 0:
        count, unit = minutes // 1440, "day"
    elif minutes % 60 == 0:
        count, unit = minutes // 60, "hour"
    else:
        count, unit = minutes, "minute"
    return f"every {unit}" if count == 1 else f"every {count} {unit}s"


# ---------------------------------------------------------------- rows


def ensure_builtin_schedules(db: Session) -> int:
    """Insert the built-in schedules that are missing. Existing rows (and whether the owner
    paused them) are left alone. Returns how many were added; commits."""
    existing = set(db.execute(select(Schedule.builtin_key).where(Schedule.kind == "builtin")).scalars())
    added = 0
    for key, (name, what, trigger_type, interval, daily) in BUILTIN_SCHEDULES.items():
        if key in existing:
            continue
        db.add(
            Schedule(
                name=name,
                kind="builtin",
                builtin_key=key,
                request_text=what,
                trigger_type=trigger_type,
                interval_minutes=interval,
                daily_time=daily,
                paused=False,
                anchor_at=utcnow().replace(microsecond=0),
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def _new_task(db: Session, schedule: Schedule, run_key: str, run_at: datetime, tz: ZoneInfo) -> Task | None:
    """The task one run of `schedule` puts into the queue (not committed), or None when this
    run should create nothing."""
    origin = {"schedule_id": schedule.id, "schedule_name": schedule.name, "run_key": run_key}
    if schedule.builtin_key == HEALTH_CHECK:
        still_open = db.execute(select(Task.id).where(Task.kind == HEALTH_CHECK, Task.status.in_(ACTIVE)).limit(1)).first()
        if still_open:  # the queue has not reached the previous check yet: do not pile them up
            return None
        return Task(
            title="Agent health check",
            description=schedule.request_text,
            created_by=f"schedule:{HEALTH_CHECK}",
            kind=HEALTH_CHECK,
            priority="high",
            input=origin,
            status=QUEUED,
        )
    if schedule.builtin_key == DAILY_REPORT:
        day = run_at.replace(tzinfo=UTC).astimezone(tz).date().isoformat()
        return Task(
            title=f"Daily report {day}",
            description=schedule.request_text,
            created_by=f"schedule:{DAILY_REPORT}",
            kind=DAILY_REPORT,
            input={**origin, "day": day, "timezone": tz.key},
            status=QUEUED,
        )
    agent = db.get(Agent, schedule.agent_id) if schedule.agent_id is not None else None
    if agent is None:
        return None
    title, _, rest = schedule.request_text.strip().partition("\n")
    return Task(
        title=title.strip()[:200] or schedule.name,
        description=rest.strip()[:4000],
        created_by=f"schedule:{schedule.id}",
        kind="scheduled",  # goes straight to its agent; the Central Manager does not route it
        assigned_agent_id=agent.id,
        input={**origin, "request": schedule.request_text.strip()},
        status=ASSIGNED,
    )


def run_schedule(
    schedule_id: int, now: datetime | None = None, session_factory: sessionmaker[Session] | None = None
) -> int | None:
    """One firing of a schedule: create its task — unless the schedule is gone or paused, or
    this scheduled run already created its task. Returns the new task's id, else None."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        schedule = db.get(Schedule, schedule_id)
        if schedule is None or schedule.paused:
            return None
        moment = now or utcnow()
        tz = village_timezone(db)
        run_at = scheduled_time(schedule, moment, tz)
        run_key = f"{schedule.id}:{run_at:%Y-%m-%dT%H:%M:%S}"
        run = ScheduleRun(schedule_id=schedule.id, run_key=run_key, fired_at=moment)
        db.add(run)
        try:
            db.flush()  # the UNIQUE run key: a second firing of the same run stops here
        except IntegrityError:
            db.rollback()
            log.info("schedule %s: run %s already created its task; nothing to do", schedule_id, run_key)
            return None
        task = _new_task(db, schedule, run_key, run_at, tz)
        if task is None:
            db.rollback()
            return None
        db.add(task)
        db.flush()
        run.task_id = task.id
        schedule.last_run_at = moment
        schedule.last_task_id = task.id
        try:
            db.commit()
        except IntegrityError:  # two firings raced: the other one won
            db.rollback()
            return None
        return task.id


def fire(schedule_id: int) -> None:
    """What APScheduler calls. It must never raise: a failed run is logged, the next one comes."""
    try:
        run_schedule(schedule_id)
    except Exception:  # noqa: BLE001
        log.exception("schedule %s: could not create its task", schedule_id)


# ---------------------------------------------------------------- APScheduler


def job_id(schedule_id: int) -> str:
    return f"schedule:{schedule_id}"


class VillageScheduler:
    """The one APScheduler of the process, started and stopped with the FastAPI lifespan."""

    def __init__(self) -> None:
        self._scheduler: Any = None
        self._lock = threading.Lock()
        self.timezone = DEFAULT_TIMEZONE

    @property
    def running(self) -> bool:
        return self._scheduler is not None and bool(self._scheduler.running)

    def start(self) -> None:
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        if self.running:
            return
        with get_session_factory()() as db:
            ensure_builtin_schedules(db)
            tz = village_timezone(db)
        self.timezone = tz.key
        self._scheduler = BackgroundScheduler(
            jobstores={"default": SQLAlchemyJobStore(engine=get_engine(), tablename="apscheduler_jobs")},
            executors={"default": ThreadPoolExecutor(2)},  # jobs only insert one row; two threads are plenty
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": None},
            timezone=tz,
        )
        self._scheduler.start()
        self.sync()
        log.info("scheduler started: %s job(s), timezone %s", len(self._scheduler.get_jobs()), tz.key)

    def stop(self) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=True)
            except Exception:  # noqa: BLE001
                log.exception("scheduler: shutdown failed")
        self._scheduler = None

    def _trigger(self, schedule: Schedule) -> Any:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        tz = ZoneInfo(self.timezone)
        if schedule.trigger_type == "daily":
            hour, minute = _clock(schedule.daily_time or "00:00")
            return CronTrigger(hour=hour, minute=minute, timezone=tz)
        return IntervalTrigger(
            minutes=schedule.interval_minutes or 1, start_date=schedule.anchor_at.replace(tzinfo=UTC), timezone=tz
        )

    def apply(self, schedule: Schedule) -> None:
        """Make the job of one schedule match its row: add it, re-time it, pause or resume it.
        A job that is already right is left alone, so a restart never resets or doubles it."""
        if not self.running:
            return
        with self._lock:
            trigger = self._trigger(schedule)
            job = self._scheduler.get_job(job_id(schedule.id))
            if job is None:
                job = self._scheduler.add_job(
                    "app.scheduler:fire",
                    trigger=trigger,
                    args=[schedule.id],
                    id=job_id(schedule.id),
                    name=schedule.name,
                    replace_existing=True,
                )
            elif repr(job.trigger) != repr(trigger):
                job = self._scheduler.reschedule_job(job.id, trigger=trigger)
            if schedule.paused and job.next_run_time is not None:
                self._scheduler.pause_job(job.id)
            elif not schedule.paused and job.next_run_time is None:
                self._scheduler.resume_job(job.id)

    def remove(self, schedule_id: int) -> None:
        if not self.running:
            return
        with self._lock:
            if self._scheduler.get_job(job_id(schedule_id)) is not None:
                self._scheduler.remove_job(job_id(schedule_id))

    def sync(self) -> None:
        """Bring every job in line with the `schedule` table; jobs without a row are removed."""
        if not self.running:
            return
        with get_session_factory()() as db:
            schedules = list(db.execute(select(Schedule)).scalars())
        for schedule in schedules:
            self.apply(schedule)
        wanted = {job_id(schedule.id) for schedule in schedules}
        with self._lock:
            for job in self._scheduler.get_jobs():
                if job.id not in wanted:
                    self._scheduler.remove_job(job.id)

    def job_ids(self) -> list[str]:
        return sorted(job.id for job in self._scheduler.get_jobs()) if self.running else []

    def job_next_run(self, schedule_id: int) -> datetime | None:
        """The next run as APScheduler itself has it (naive UTC); None when paused or unknown."""
        if not self.running:
            return None
        job = self._scheduler.get_job(job_id(schedule_id))
        if job is None or job.next_run_time is None:
            return None
        return job.next_run_time.astimezone(UTC).replace(tzinfo=None)

    def run_now(self, schedule_id: int) -> None:
        """Make a job due immediately (tests)."""
        self._scheduler.modify_job(job_id(schedule_id), next_run_time=datetime.now(UTC))


_scheduler = VillageScheduler()


def get_scheduler() -> VillageScheduler:
    return _scheduler
