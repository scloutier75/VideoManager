import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..config import settings
from ..database import AsyncSessionLocal
from .scanner import run_scan

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _scheduled_scan():
    async with AsyncSessionLocal() as db:
        await run_scan(db)


async def start_scheduler():
    if settings.scan_interval_minutes > 0:
        scheduler.add_job(
            _scheduled_scan,
            trigger="interval",
            minutes=settings.scan_interval_minutes,
            id="periodic_scan",
            replace_existing=True,
        )
        logger.info(
            f"[Scheduler] Auto-scan every {settings.scan_interval_minutes} minute(s)"
        )
    scheduler.start()

    # Kick off an immediate scan in the background without blocking startup
    logger.info("[Scheduler] Running initial scan on startup…")
    asyncio.ensure_future(_startup_scan())


async def _startup_scan():
    await _scheduled_scan()
    _log_next_run()


def _log_next_run():
    if settings.scan_interval_minutes <= 0:
        return
    job = scheduler.get_job("periodic_scan")
    if job and job.next_run_time:
        local_time = job.next_run_time.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        logger.info(f"[Scheduler] Next scheduled scan at: {local_time}")


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def trigger_scan_now():
    """Called by the API to start an immediate scan in the background."""
    async with AsyncSessionLocal() as db:
        result = await run_scan(db)
    _log_next_run()
    return result
