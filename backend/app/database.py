import re
import asyncpg
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_database_if_not_exists():
    """Connect to the default 'postgres' database and create VideoManager if missing."""
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/")

    if not re.match(r"^[a-zA-Z0-9_]+$", db_name):
        raise ValueError(f"Unsafe database name detected: {db_name}")

    try:
        conn = await asyncpg.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "postgres",
            password=parsed.password or "",
            database="postgres",
        )
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[DB] Created database '{db_name}'")
        else:
            print(f"[DB] Database '{db_name}' already exists")
        await conn.close()
    except Exception as e:
        print(f"[DB] Warning: could not check/create database: {e}")
