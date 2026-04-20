from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ..database import get_db
from .. import crud
from ..schemas import VideoResponse, VideoListResponse, VideoStatsResponse

router = APIRouter()


@router.get("/stats", response_model=VideoStatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    return await crud.get_video_stats(db)


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None, max_length=200),
    min_score: Optional[float] = Query(default=None, ge=0, le=10),
    max_score: Optional[float] = Query(default=None, ge=0, le=10),
    min_efficiency: Optional[float] = Query(default=None, ge=0),
    max_efficiency: Optional[float] = Query(default=None, ge=0),
    codec: Optional[str] = Query(default=None, max_length=50),
    sort_by: str = Query(default="score"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.get_videos(
        db,
        page=page,
        limit=limit,
        search=search,
        min_score=min_score,
        max_score=max_score,
        min_efficiency=min_efficiency,
        max_efficiency=max_efficiency,
        codec=codec,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return VideoListResponse(total=total, page=page, limit=limit, items=items)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    await crud.delete_video(db, video_id)
