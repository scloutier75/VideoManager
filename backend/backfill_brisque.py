"""
Backfill brisque_score for all videos in the database that currently have NULL.

Usage (from backend/ with venv activated):
    python backfill_brisque.py [--frames N] [--concurrency N] [--dry-run]

Options:
    --frames N       Number of frames to sample per video (default: 5)
    --concurrency N  Number of videos to process in parallel (default: 2)
    --dry-run        Score files but do not write to the database
    --limit N        Stop after N videos (useful for testing)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

# Allow importing app modules from this script
sys.path.insert(0, str(Path(__file__).parent))
from app.config import settings
from app.worker.brisque import score_video_brisque

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_brisque")


async def fetch_pending(conn, limit=None):
    """Return rows (id, filepath) where brisque_score IS NULL."""
    q = "SELECT id, filepath FROM videos WHERE brisque_score IS NULL ORDER BY id"
    if limit:
        q += f" LIMIT {int(limit)}"
    return await conn.fetch(q)


async def update_score(conn, video_id: int, score: float):
    await conn.execute(
        "UPDATE videos SET brisque_score = $1 WHERE id = $2",
        score, video_id,
    )


async def process_video(conn, row, n_frames: int, dry_run: bool, sem: asyncio.Semaphore):
    video_id = row["id"]
    filepath = row["filepath"]

    async with sem:
        logger.info(f"[{video_id}] Scoring  {Path(filepath).name}")

        if not Path(filepath).exists():
            logger.warning(f"[{video_id}] File not found, skipping: {filepath}")
            return

        try:
            loop = asyncio.get_event_loop()
            score = await loop.run_in_executor(
                None, score_video_brisque, filepath, n_frames
            )
        except Exception as e:
            logger.error(f"[{video_id}] BRISQUE error ({Path(filepath).name}): {e}")
            return

        if score is None:
            logger.warning(f"[{video_id}] No score produced for: {filepath}")
            return

        logger.info(f"[{video_id}] Score={score:.1f}  {'(dry-run, not saved)' if dry_run else ''}")
        if not dry_run:
            await update_score(conn, video_id, score)


async def main(args):
    dsn = settings.database_url.replace("+asyncpg", "")  # asyncpg uses plain postgres://
    conn = await asyncpg.connect(dsn)

    rows = await fetch_pending(conn, limit=args.limit)
    total = len(rows)
    if total == 0:
        logger.info("No videos with NULL brisque_score found — nothing to do.")
        await conn.close()
        return

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info(
        f"Found {total} video(s) to backfill  "
        f"[frames={args.frames}, concurrency={args.concurrency}, mode={mode}]"
    )

    sem = asyncio.Semaphore(args.concurrency)
    tasks = [
        process_video(conn, row, args.frames, args.dry_run, sem)
        for row in rows
    ]
    await asyncio.gather(*tasks)

    logger.info("Backfill complete.")
    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill brisque_score for existing videos")
    parser.add_argument("--frames",      type=int, default=5,  help="Frames to sample per video")
    parser.add_argument("--concurrency", type=int, default=2,  help="Parallel videos")
    parser.add_argument("--dry-run",     action="store_true",  help="Score but don't save")
    parser.add_argument("--limit",       type=int, default=None, help="Max videos to process")
    args = parser.parse_args()

    asyncio.run(main(args))
