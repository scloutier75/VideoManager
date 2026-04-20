from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class VideoResponse(BaseModel):
    id: int
    filename: str
    filepath: str
    directory: str
    file_size: Optional[int] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_codec: Optional[str] = None
    video_bitrate: Optional[int] = None
    audio_codec: Optional[str] = None
    audio_bitrate: Optional[int] = None
    frame_rate: Optional[float] = None
    container_format: Optional[str] = None
    score: Optional[float] = None
    score_breakdown: Optional[Any] = None
    efficiency_score: Optional[float] = None
    brisque_score: Optional[float] = None
    file_mtime: Optional[float] = None
    scanned_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class VideoListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[VideoResponse]


class VideoStatsResponse(BaseModel):
    total: int
    avg_score: Optional[float] = None
    max_score: Optional[float] = None
    min_score: Optional[float] = None


class ScanConfigCreate(BaseModel):
    folder_path: str
    recursive: bool = True


class ScanConfigResponse(BaseModel):
    id: int
    folder_path: str
    is_active: bool
    recursive: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScanJobResponse(BaseModel):
    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    files_found: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_error: int = 0
    status: str
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}
