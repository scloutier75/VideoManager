import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from .. import crud
from ..schemas import ScanJobResponse, ScanConfigCreate, ScanConfigResponse
from ..worker.scheduler import trigger_scan_now

router = APIRouter()


@router.post("/start", response_model=dict)
async def start_scan(background_tasks: BackgroundTasks):
    """Trigger an immediate folder scan in the background."""
    background_tasks.add_task(trigger_scan_now)
    return {"message": "Scan started"}


@router.get("/status", response_model=ScanJobResponse | dict)
async def get_scan_status(db: AsyncSession = Depends(get_db)):
    """Return the currently running job, or the most recent completed job."""
    running = await crud.get_current_scan_job(db)
    if running:
        return running
    recent = await crud.get_recent_scan_jobs(db, limit=1)
    if recent:
        return recent[0]
    return {"status": "idle", "message": "No scans have been run yet"}


@router.get("/history", response_model=List[ScanJobResponse])
async def get_scan_history(db: AsyncSession = Depends(get_db)):
    return await crud.get_recent_scan_jobs(db, limit=20)


@router.get("/configs", response_model=List[ScanConfigResponse])
async def list_scan_configs(db: AsyncSession = Depends(get_db)):
    return await crud.get_all_scan_configs(db)


@router.post("/configs", response_model=ScanConfigResponse, status_code=201)
async def add_scan_config(
    payload: ScanConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    return await crud.create_scan_config(db, payload.folder_path, payload.recursive)


@router.delete("/configs/{config_id}", status_code=204)
async def remove_scan_config(config_id: int, db: AsyncSession = Depends(get_db)):
    configs = await crud.get_all_scan_configs(db)
    if not any(c.id == config_id for c in configs):
        raise HTTPException(status_code=404, detail="Config not found")
    await crud.delete_scan_config(db, config_id)
