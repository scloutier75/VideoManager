import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import create_database_if_not_exists, init_db
from .worker.scheduler import start_scheduler, stop_scheduler
from .api import videos, scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_database_if_not_exists()
    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()


app = FastAPI(
    title="VideoManager API",
    description="Scans folders for video files and rates their quality.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])


@app.get("/api/health", tags=["health"])
async def health():
    return {"status": "ok"}
