"""ShopPilot scheduler — runs research and idea generation on a cadence.

Design notes:

- AsyncIOScheduler is used so jobs run inside the FastAPI event loop.
- Each job opens its own DB session (the FastAPI request-scoped session is
  not available outside a request).
- `research_job` runs every RESEARCH_INTERVAL_HOURS (default 24h).
  When it finishes, it schedules a one-shot `idea_job` for IDEA_DELAY_AFTER_RESEARCH
  minutes later. Chaining via a one-shot job (rather than a fixed interval)
  keeps the timing correct even if research runs late.
- Supplier / design / listing / marketing agents stay manually-triggered via
  the dashboard buttons — they each have a human-approval gate (approving
  ideas, reviewing generated artwork, sanity-checking live listings and social
  copy) that we don't want to bypass automatically yet. Their endpoints already
  exist for when we're ready to chain them. The full pipeline order is:
  research_agent → idea_agent → supplier_agent → design_agent → listing_agent
  → marketing_agent

The scheduler is started from main.py's `lifespan` context manager so it
shuts down cleanly with the app.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agents import design_agent, idea_agent, listing_agent, marketing_agent, research_agent, supplier_agent  # noqa: F401
from database import SessionLocal

logger = logging.getLogger("shoppilot.scheduler")

# Cadence — tweak these to change how often the agents run.
RESEARCH_INTERVAL_HOURS = 24
IDEA_DELAY_AFTER_RESEARCH_MINUTES = 60

# Job IDs (constants so we can look them up / replace them).
RESEARCH_JOB_ID = "research_job"
IDEA_JOB_ID = "idea_job"

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton scheduler. Created lazily on first call."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _run_research_job() -> None:
    """Run the research agent, then schedule a one-shot idea_job."""
    logger.info("scheduler: research_job starting")
    db = SessionLocal()
    try:
        result = await research_agent.run(db)
        logger.info("scheduler: research_job done — %s", result)
    except Exception as e:
        logger.exception("scheduler: research_job failed: %s", e)
        return
    finally:
        db.close()

    # Chain: schedule a one-shot idea_job IDEA_DELAY_AFTER_RESEARCH_MINUTES from now.
    run_at = datetime.now(timezone.utc) + timedelta(
        minutes=IDEA_DELAY_AFTER_RESEARCH_MINUTES
    )
    sched = get_scheduler()
    # `replace_existing=True` so a back-to-back research run doesn't pile up
    # multiple pending idea_jobs.
    sched.add_job(
        _run_idea_job,
        trigger=DateTrigger(run_date=run_at),
        id=IDEA_JOB_ID,
        replace_existing=True,
    )
    logger.info(
        "scheduler: idea_job queued for %s (in %d min)",
        run_at.isoformat(),
        IDEA_DELAY_AFTER_RESEARCH_MINUTES,
    )


async def _run_idea_job() -> None:
    """Run the idea agent. No further chaining — supplier/listing/marketing
    require human approval gates and are triggered manually."""
    logger.info("scheduler: idea_job starting")
    db = SessionLocal()
    try:
        result = await idea_agent.run(db)
        logger.info("scheduler: idea_job done — %s", result)
    except Exception as e:
        logger.exception("scheduler: idea_job failed: %s", e)
    finally:
        db.close()


def start() -> AsyncIOScheduler:
    """Configure jobs and start the scheduler. Idempotent — re-running on a
    hot reload won't double-schedule."""
    sched = get_scheduler()
    sched.add_job(
        _run_research_job,
        trigger=IntervalTrigger(hours=RESEARCH_INTERVAL_HOURS),
        id=RESEARCH_JOB_ID,
        replace_existing=True,
    )
    if not sched.running:
        sched.start()
    logger.info(
        "scheduler: started — research every %dh, idea chained +%dmin",
        RESEARCH_INTERVAL_HOURS,
        IDEA_DELAY_AFTER_RESEARCH_MINUTES,
    )
    return sched


def shutdown() -> None:
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("scheduler: shut down")


def list_jobs() -> list[dict[str, Any]]:
    """Snapshot of currently-scheduled jobs for the dashboard."""
    sched = get_scheduler()
    out: list[dict[str, Any]] = []
    for job in sched.get_jobs():
        out.append({
            "id": job.id,
            "name": job.name or job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return out


async def trigger_research_now() -> dict[str, Any]:
    """Manually run the research job out-of-cycle. Useful for testing or for a
    'kick it now' button in the dashboard. Returns the research agent's result.
    """
    logger.info("scheduler: research_job triggered manually")
    db = SessionLocal()
    try:
        result = await research_agent.run(db)
    finally:
        db.close()
    # Still chain into an idea_job so the manual-trigger behaves like the
    # scheduled one.
    run_at = datetime.now(timezone.utc) + timedelta(
        minutes=IDEA_DELAY_AFTER_RESEARCH_MINUTES
    )
    sched = get_scheduler()
    sched.add_job(
        _run_idea_job,
        trigger=DateTrigger(run_date=run_at),
        id=IDEA_JOB_ID,
        replace_existing=True,
    )
    return {"research": result, "idea_job_queued_for": run_at.isoformat()}
