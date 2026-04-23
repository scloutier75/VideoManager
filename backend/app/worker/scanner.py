import os
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud
from ..config import settings
from .analyzer import VIDEO_EXTENSIONS, probe_video, extract_video_info
from .brisque import score_video_brisque

logger = logging.getLogger(__name__)

# Path for the scan failure log — lives in the backend/ directory
_SCAN_FAILURE_LOG = Path(__file__).parent.parent.parent / "scan_failures.log"


def _log_failure(filepath: str, stage: str, reason: str) -> None:
    """
    Append one structured line to scan_failures.log.

    Args:
        filepath: Full path to the video file.
        stage:    'ffprobe' | 'brisque' | 'exception'
        reason:   Human-readable description of what went wrong.
    """
    filename = Path(filepath).name
    directory = str(Path(filepath).parent)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}]  stage={stage:<10}  file={filename!r}  path={directory!r}  reason={reason}\n"
    try:
        with open(_SCAN_FAILURE_LOG, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.warning(f"[Scanner] Could not write scan_failures.log: {exc}")

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

                        # Skip only when the file is truly unchanged AND brisque
                        # does not need a retry (i.e. it either succeeded or is disabled).
                        brisque_needs_retry = (
                            settings.brisque_enabled
                            and existing is not None
                            and existing.brisque_score is None
                        )
                        if existing and existing.file_mtime == file_mtime and not brisque_needs_retry:
                            skipped += 1
                            logger.info(f"[Scanner]   SKIP  {filename}  (unchanged)")
                            continue
                        if brisque_needs_retry and existing.file_mtime == file_mtime:
                            logger.info(f"[Scanner]   RETRY {filename}  (brisque score missing)")

                        # ffprobe is blocking – run in thread pool
                        probe_data, probe_error = await loop.run_in_executor(
                            None, probe_video, filepath
                        )
                        if probe_data is None:
                            # Determine if this is a permanent corruption vs. transient error.
                            # ffprobe's own "Invalid data" / "EBML" / "moov atom" messages
                            # indicate a corrupt/unplayable file with high confidence.
                            corrupt_keywords = (
                                "invalid data", "ebml", "moov atom",
                                "no such file", "end of file", "invalid argument",
                                "header parsing failed", "no streams",
                            )
                            is_corrupt = any(
                                kw in (probe_error or "").lower()
                                for kw in corrupt_keywords
                            )
                            logger.warning(
                                f"[Scanner]   ERR   {filename}  "
                                f"({'CORRUPT' if is_corrupt else 'probe-err'}: {probe_error})"
                            )
                            _log_failure(
                                filepath, "ffprobe",
                                probe_error or "ffprobe returned no data"
                            )
                            # Persist corrupt flag so the UI can surface it
                            if is_corrupt:
                                if existing:
                                    await crud.update_video(db, existing.id, {"is_corrupt": True})
                                else:
                                    # Insert a minimal record so the file appears in the UI
                                    stub = {
                                        "filename": filename,
                                        "filepath": filepath,
                                        "directory": str(Path(filepath).parent),
                                        "file_size": file_size,
                                        "file_mtime": file_mtime,
                                        "is_corrupt": True,
                                    }
                                    await crud.create_video(db, stub)
                            errors += 1
                            continue

                        video_info = extract_video_info(
                            probe_data, filepath, file_size, file_mtime
                        )
                        # File is readable — clear any stale corrupt flag
                        video_info["is_corrupt"] = False

                        # Optional BRISQUE perceptual scoring (slow)
                        if settings.brisque_enabled:
                            brisque_score, brisque_fail_reason = await loop.run_in_executor(
                                None, score_video_brisque, filepath, settings.brisque_frames
                            )
                            video_info["brisque_score"] = brisque_score
                            if brisque_score is not None:
                                brisque_str = f"  brisque={brisque_score:.1f}/10"
                            else:
                                brisque_str = "  brisque=err"
                                _log_failure(filepath, "brisque", brisque_fail_reason or "unknown error")
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
                        _log_failure(filepath, "exception", f"{type(exc).__name__}: {exc}")
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
