import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/VideoManager"
    scan_folders: str = ""
    scan_interval_minutes: int = 60
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # BRISQUE perceptual scoring — slow, runs ffmpeg frame extraction per video
    brisque_enabled: bool = False
    brisque_frames: int = 8  # number of frames sampled per video

    @property
    def scan_folders_list(self) -> List[str]:
        if not self.scan_folders:
            return []
        result = []
        for f in self.scan_folders.split(","):
            f = f.strip()
            if not f:
                continue
            # Expand ~ and ~user, then resolve relative paths to absolute
            f = os.path.expanduser(f)
            f = os.path.abspath(f)
            result.append(f)
        return result

    model_config = {"env_file": ".env"}


settings = Settings()
