import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from .config import settings

logger = logging.getLogger(__name__)

USE_POSTGRES = bool(settings.database_url)

if USE_POSTGRES:
    import asyncpg

if TYPE_CHECKING:
    if USE_POSTGRES:
        _pg_pool: asyncpg.Pool | None = None
    else:
        _pg_pool = None
else:
    _pg_pool = None

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS yt_tokens (
        session_id TEXT PRIMARY KEY,
        refresh_token TEXT NOT NULL,
        access_token TEXT,
        token_expiry DOUBLE PRECISION,
        client_id TEXT NOT NULL,
        client_secret TEXT NOT NULL,
        token_uri TEXT NOT NULL,
        channel_title TEXT,
        channel_id TEXT,
        created_at DOUBLE PRECISION NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL
    )
"""


def _ensure_db_dir():
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_db():
    if USE_POSTGRES:
        global _pg_pool
        _pg_pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
        async with _pg_pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)
        logger.info("PostgreSQL token database initialized")
    else:
        _ensure_db_dir()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(_CREATE_TABLE_SQL)
            await db.commit()
        logger.info("SQLite token database initialized")


async def store_token(
    session_id: str,
    refresh_token: str,
    access_token: str | None,
    expiry: float | None,
    client_id: str,
    client_secret: str,
    token_uri: str,
    channel_title: str | None = None,
    channel_id: str | None = None,
):
    now = time.time()
    if USE_POSTGRES:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO yt_tokens
                   (session_id, refresh_token, access_token, token_expiry,
                    client_id, client_secret, token_uri, channel_title, channel_id,
                    created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                   ON CONFLICT (session_id) DO UPDATE SET
                    refresh_token = EXCLUDED.refresh_token,
                    access_token = EXCLUDED.access_token,
                    token_expiry = EXCLUDED.token_expiry,
                    client_id = EXCLUDED.client_id,
                    client_secret = EXCLUDED.client_secret,
                    token_uri = EXCLUDED.token_uri,
                    channel_title = EXCLUDED.channel_title,
                    channel_id = EXCLUDED.channel_id,
                    updated_at = EXCLUDED.updated_at""",
                session_id, refresh_token, access_token, expiry,
                client_id, client_secret, token_uri, channel_title, channel_id,
                now, now,
            )
    else:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO yt_tokens
                   (session_id, refresh_token, access_token, token_expiry,
                    client_id, client_secret, token_uri, channel_title, channel_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, refresh_token, access_token, expiry,
                 client_id, client_secret, token_uri, channel_title, channel_id,
                 now, now),
            )
            await db.commit()


async def get_token(session_id: str) -> dict | None:
    if USE_POSTGRES:
        async with _pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM yt_tokens WHERE session_id = $1", session_id
            )
            if row:
                return dict(row)
        return None
    else:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM yt_tokens WHERE session_id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None


async def update_access_token(session_id: str, access_token: str, expiry: float):
    if USE_POSTGRES:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE yt_tokens SET access_token = $1, token_expiry = $2, updated_at = $3 WHERE session_id = $4",
                access_token, expiry, time.time(), session_id,
            )
    else:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                "UPDATE yt_tokens SET access_token = ?, token_expiry = ?, updated_at = ? WHERE session_id = ?",
                (access_token, expiry, time.time(), session_id),
            )
            await db.commit()


async def delete_token(session_id: str):
    if USE_POSTGRES:
        async with _pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM yt_tokens WHERE session_id = $1", session_id)
    else:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("DELETE FROM yt_tokens WHERE session_id = ?", (session_id,))
            await db.commit()


async def get_all_tokens() -> list[dict]:
    if USE_POSTGRES:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM yt_tokens ORDER BY created_at DESC")
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM yt_tokens ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
