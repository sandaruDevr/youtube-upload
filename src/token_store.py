import asyncio
import logging

import httpx
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .config import settings

logger = logging.getLogger(__name__)

FIREBASE_DB_URL = settings.firebase_db_url


async def verify_firebase_token(id_token_str: str) -> dict | None:
    """Verify a Firebase ID token and return the decoded payload (incl. uid)."""
    try:
        decoded = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            id_token_str,
            google_requests.Request(),
            audience=settings.firebase_web_api_key,
        )
        logger.info("Firebase token verified for uid=%s", decoded.get("uid") or decoded.get("sub"))
        return decoded
    except Exception as e:
        logger.error("Firebase token verification failed: %s", e)
        return None


async def get_refresh_token(uid: str, id_token_str: str) -> str | None:
    """Read the YouTube refresh token from Firebase Realtime DB for the given UID."""
    url = f"{FIREBASE_DB_URL}/users/{uid}/youtube_refresh_token.json"
    params = {"auth": id_token_str}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, str):
                return data
            return None
    except Exception:
        logger.exception("Failed to read refresh token from Firebase DB for uid=%s", uid)
        return None


async def delete_refresh_token(uid: str, id_token_str: str) -> bool:
    """Delete the YouTube refresh token from Firebase Realtime DB."""
    url = f"{FIREBASE_DB_URL}/users/{uid}/youtube_refresh_token.json"
    params = {"auth": id_token_str}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(url, params=params)
            resp.raise_for_status()
            return True
    except Exception:
        logger.exception("Failed to delete refresh token from Firebase DB for uid=%s", uid)
        return False
