import json
import logging
import time
from pathlib import Path

import aiosqlite

from .config import settings

logger = logging.getLogger(__name__)


def _ensure_db_dir():
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_db():
    _ensure_db_dir()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS yt_tokens (
                session_id TEXT PRIMARY KEY,
                refresh_token TEXT NOT NULL,
                access_token TEXT,
                token_expiry REAL,
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                token_uri TEXT NOT NULL,
                channel_title TEXT,
                channel_id TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await db.commit()


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
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "UPDATE yt_tokens SET access_token = ?, token_expiry = ?, updated_at = ? WHERE session_id = ?",
            (access_token, expiry, time.time(), session_id),
        )
        await db.commit()


async def delete_token(session_id: str):
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM yt_tokens WHERE session_id = ?", (session_id,))
        await db.commit()


async def get_all_tokens() -> list[dict]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM yt_tokens ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
