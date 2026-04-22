import os
import asyncio
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud
from ..config import settings
from .analyzer import VIDEO_EXTENSIONS, probe_video, extract_video_info
from .brisque import score_video_brisque

logger = logging.getLogger(__name__)

# Simple in-process lock to prevent concurrent scans
_scan_running = False


async def run_scan(db: AsyncSession) -> dict:
    """
    Scan all configured folders for video files, analyse each one with ffprobe,
    compute a quality score, and persist results to the database.

    Returns a summary dict with counts.
    """
    global _scan_running
    if _scan_running:
        logger.info("[Scanner] Scan already in progress – skipping.")
        return {"status": "already_running"}

    _scan_running = True
    job = await crud.create_scan_job(db)
    logger.info(f"[Scanner] Started scan job #{job.id}")

    found = processed = skipped = errors = 0

    # Track all filepaths seen on disk during this scan
    seen_filepaths: set = set()

    try:
        # Collect folders from .env and from the database
        env_folders = settings.scan_folders_list
        db_configs = await crud.get_active_scan_configs(db)
        db_folders = [c.folder_path for c in db_configs]
        all_folders = list({*env_folders, *db_folders})

        loop = asyncio.get_event_loop()

        for folder in all_folders:
            if not os.path.isdir(folder):
                logger.warning(f"[Scanner] Folder not found – skipping: {folder}")
                continue

            folder_video_count = 0
            logger.info(f"[Scanner] ── Scanning folder: {folder}")
            for root, _dirs, files in os.walk(folder):
                for filename in files:
                    if Path(filename).suffix.lower() not in VIDEO_EXTENSIONS:
                        continue

                    filepath = os.path.join(root, filename)
                    found += 1
                    seen_filepaths.add(filepath)

                    try:
                        stat = os.stat(filepath)
                        file_mtime = stat.st_mtime
                        file_size = stat.st_size

                        existing = await crud.get_video_by_path(db, filepath)
                        if existing and existing.file_mtime == file_mtime:
                            skipped += 1
                            logger.info(f"[Scanner]   SKIP  {filename}  (unchanged)")
                            continue

                        # ffprobe is blocking – run in thread pool
                        probe_data = await loop.run_in_executor(
                            None, probe_video, filepath
                        )
                        if probe_data is None:
                            logger.warning(f"[Scanner]   ERR   {filename}  (ffprobe failed)")
                            errors += 1
                            continue

                        video_info = extract_video_info(
                            probe_data, filepath, file_size, file_mtime
                        )

                        # Optional BRISQUE perceptual scoring (slow)
                        if settings.brisque_enabled:
                            brisque_score = await loop.run_in_executor(
                                None, score_video_brisque, filepath, settings.brisque_frames
                            )
                            video_info["brisque_score"] = brisque_score
                            brisque_str = (
                                f"  brisque={brisque_score:.1f}/10" if brisque_score is not None else "  brisque=err"
                            )
                        else:
                            brisque_str = ""

                        action = "UPDATE" if existing else "NEW   "
                        res_str = (
                            f"{video_info['width']}x{video_info['height']}"
                            if video_info.get('width') else "?"
                        )
                        codec_str = video_info.get('video_codec') or "?"
                        score_str = f"{video_info['score']:.1f}/10"
                        logger.info(
                            f"[Scanner]   {action} {filename}  "
                            f"[{res_str}  {codec_str}  score={score_str}{brisque_str}]"
                        )

                        if existing:
                            await crud.update_video(db, existing.id, video_info)
                        else:
                            await crud.create_video(db, video_info)

                        processed += 1
                        folder_video_count += 1

                    except Exception as exc:
                        logger.error(f"[Scanner]   ERR   {filepath}: {exc}")
                        errors += 1
                        # Roll back any pending transaction so the session stays usable
                        try:
                            await db.rollback()
                        except Exception:
                            pass

            logger.info(f"[Scanner] ── Done with folder: {folder}  ({folder_video_count} processed)")

        # After scanning all folders, flag any DB records whose files are gone
        newly_missing = await crud.mark_missing_videos(db, seen_filepaths)
        if newly_missing:
            logger.warning(f"[Scanner] {newly_missing} file(s) flagged as missing (no longer found on disk)")

        await crud.complete_scan_job(
            db, job.id, found, processed, skipped, errors, status="completed"
        )
        logger.info(
            f"[Scanner] Scan #{job.id} complete – "
            f"found={found} processed={processed} skipped={skipped} errors={errors}"
        )

    except Exception as exc:
        logger.error(f"[Scanner] Scan failed: {exc}")
        await crud.complete_scan_job(
            db, job.id, found, processed, skipped, errors,
            status="failed", error_message=str(exc)
        )
    finally:
        _scan_running = False

    return {
        "job_id": job.id,
        "status": "completed",
        "files_found": found,
        "files_processed": processed,
        "files_skipped": skipped,
        "files_error": errors,
    }
