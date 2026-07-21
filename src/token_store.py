import asyncio
import logging

import httpx
import jwt
from jwt import PyJWKClient

from .config import settings

logger = logging.getLogger(__name__)

FIREBASE_DB_URL = settings.firebase_db_url
FIREBASE_PROJECT_ID = settings.firebase_project_id

_jwks_client = PyJWKClient(
    f"https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
)


async def verify_firebase_token(id_token_str: str) -> dict | None:
    """Verify a Firebase ID token and return the decoded payload (incl. uid)."""
    try:
        signing_key = await asyncio.to_thread(_jwks_client.get_signing_key_from_jwt, id_token_str)
        decoded = jwt.decode(
            id_token_str,
            signing_key.key,
            algorithms=["RS256"],
            audience=FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}",
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
