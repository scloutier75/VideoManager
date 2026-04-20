from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, asc, update, delete
from .models import Video, ScanConfig, ScanJob


# ── Video ──────────────────────────────────────────────────────────────────────

async def get_videos(
    db: AsyncSession,
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    min_efficiency: Optional[float] = None,
    max_efficiency: Optional[float] = None,
    codec: Optional[str] = None,
    sort_by: str = "score",
    sort_order: str = "desc",
) -> tuple[list, int]:
    ALLOWED_SORT = {"score", "filename", "created_at", "scanned_at", "file_size", "duration", "height", "efficiency_score", "brisque_score"}
    if sort_by not in ALLOWED_SORT:
        sort_by = "score"

    query = select(Video)
    count_query = select(func.count(Video.id))

    if search:
        filt = or_(
            Video.filename.ilike(f"%{search}%"),
            Video.filepath.ilike(f"%{search}%"),
        )
        query = query.where(filt)
        count_query = count_query.where(filt)

    if min_score is not None:
        query = query.where(Video.score >= min_score)
        count_query = count_query.where(Video.score >= min_score)

    if max_score is not None:
        query = query.where(Video.score <= max_score)
        count_query = count_query.where(Video.score <= max_score)

    if min_efficiency is not None:
        query = query.where(Video.efficiency_score >= min_efficiency)
        count_query = count_query.where(Video.efficiency_score >= min_efficiency)

    if max_efficiency is not None:
        query = query.where(Video.efficiency_score <= max_efficiency)
        count_query = count_query.where(Video.efficiency_score <= max_efficiency)

    if codec:
        query = query.where(Video.video_codec.ilike(f"%{codec}%"))
        count_query = count_query.where(Video.video_codec.ilike(f"%{codec}%"))

    sort_col = getattr(Video, sort_by, Video.score)
    order_fn = desc if sort_order == "desc" else asc
    query = query.order_by(order_fn(sort_col).nulls_last())

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    total_result = await db.execute(count_query)
    return result.scalars().all(), (total_result.scalar() or 0)


async def get_video_stats(db: AsyncSession) -> dict:
    result = await db.execute(
        select(
            func.count(Video.id),
            func.avg(Video.score),
            func.max(Video.score),
            func.min(Video.score),
        )
    )
    row = result.one()
    return {
        "total": row[0] or 0,
        "avg_score": round(row[1], 1) if row[1] is not None else None,
        "max_score": row[2],
        "min_score": row[3],
    }


async def get_video_by_id(db: AsyncSession, video_id: int) -> Optional[Video]:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def get_video_by_path(db: AsyncSession, filepath: str) -> Optional[Video]:
    result = await db.execute(select(Video).where(Video.filepath == filepath))
    return result.scalar_one_or_none()


async def create_video(db: AsyncSession, data: dict) -> Video:
    video = Video(**data)
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


async def update_video(db: AsyncSession, video_id: int, data: dict) -> Video:
    await db.execute(update(Video).where(Video.id == video_id).values(**data))
    await db.commit()
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one()


async def delete_video(db: AsyncSession, video_id: int):
    await db.execute(delete(Video).where(Video.id == video_id))
    await db.commit()


# ── ScanConfig ─────────────────────────────────────────────────────────────────

async def get_all_scan_configs(db: AsyncSession) -> list:
    result = await db.execute(select(ScanConfig).order_by(ScanConfig.id))
    return result.scalars().all()


async def get_active_scan_configs(db: AsyncSession) -> list:
    result = await db.execute(
        select(ScanConfig).where(ScanConfig.is_active == True)
    )
    return result.scalars().all()


async def create_scan_config(db: AsyncSession, folder_path: str, recursive: bool = True) -> ScanConfig:
    cfg = ScanConfig(folder_path=folder_path, recursive=recursive)
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def delete_scan_config(db: AsyncSession, config_id: int):
    await db.execute(delete(ScanConfig).where(ScanConfig.id == config_id))
    await db.commit()


# ── ScanJob ────────────────────────────────────────────────────────────────────

async def create_scan_job(db: AsyncSession) -> ScanJob:
    job = ScanJob(status="running")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def complete_scan_job(
    db: AsyncSession,
    job_id: int,
    files_found: int,
    files_processed: int,
    files_skipped: int,
    files_error: int,
    status: str = "completed",
    error_message: Optional[str] = None,
):
    await db.execute(
        update(ScanJob).where(ScanJob.id == job_id).values(
            completed_at=datetime.now(timezone.utc),
            files_found=files_found,
            files_processed=files_processed,
            files_skipped=files_skipped,
            files_error=files_error,
            status=status,
            error_message=error_message,
        )
    )
    await db.commit()


async def get_current_scan_job(db: AsyncSession) -> Optional[ScanJob]:
    result = await db.execute(
        select(ScanJob)
        .where(ScanJob.status == "running")
        .order_by(desc(ScanJob.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_recent_scan_jobs(db: AsyncSession, limit: int = 10) -> list:
    result = await db.execute(
        select(ScanJob).order_by(desc(ScanJob.started_at)).limit(limit)
    )
    return result.scalars().all()
