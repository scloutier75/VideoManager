"""
Standalone worker entry-point – runs a single scan and exits.

Usage:
    cd backend
    source venv/bin/activate
    python worker.py
"""
import asyncio
import logging
from app.database import create_database_if_not_exists, init_db, AsyncSessionLocal
from app.worker.scanner import run_scan

logging.basicConfig(level=logging.INFO)


async def main():
    await create_database_if_not_exists()
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await run_scan(db)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
