from sqlalchemy import (
    Column, Integer, String, Float, BigInteger,
    DateTime, JSON, Boolean, Text
)
from sqlalchemy.sql import func
from .database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    filepath = Column(String(2000), nullable=False, unique=True, index=True)
    directory = Column(String(2000), nullable=False)
    file_size = Column(BigInteger)
    duration = Column(Float)          # seconds
    width = Column(Integer)
    height = Column(Integer)
    video_codec = Column(String(100))
    video_bitrate = Column(BigInteger)  # bps
    audio_codec = Column(String(100))
    audio_bitrate = Column(BigInteger)  # bps
    frame_rate = Column(Float)
    container_format = Column(String(100))
    score = Column(Float, index=True)
    score_breakdown = Column(JSON)
    efficiency_score = Column(Float, index=True)  # score per GB
    brisque_score = Column(Float, index=True)     # perceptual quality 0-10 (higher = better)
    file_mtime = Column(Float)          # Unix timestamp for change detection
    scanned_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScanConfig(Base):
    __tablename__ = "scan_configs"

    id = Column(Integer, primary_key=True, index=True)
    folder_path = Column(String(2000), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    recursive = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    files_found = Column(Integer, default=0)
    files_processed = Column(Integer, default=0)
    files_skipped = Column(Integer, default=0)
    files_error = Column(Integer, default=0)
    status = Column(String(50), default="running")  # running | completed | failed
    error_message = Column(Text)
