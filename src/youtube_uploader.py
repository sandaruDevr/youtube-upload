import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Token file for storing the refresh token locally
TOKEN_FILE = Path("token.json")


def _get_credentials(refresh_token: str | None = None) -> Credentials:
    """Build credentials from a refresh token.

    If refresh_token is provided, use it directly.
    Otherwise fall back to env var or token file.
    """
    if not refresh_token:
        refresh_token = settings.youtube_refresh_token

    if not refresh_token:
        if TOKEN_FILE.exists():
            import json
            token_data = json.loads(TOKEN_FILE.read_text())
            refresh_token = token_data.get("refresh_token")

    if not refresh_token:
        raise RuntimeError(
            "No YouTube refresh token found. Connect your YouTube account "
            "via the web UI or run `python -m src.oauth_setup` locally."
        )

    secret = settings.client_secret_dict
    if not secret:
        raise RuntimeError(
            "No YouTube client secret found. Set YOUTUBE_CLIENT_SECRET_JSON env var "
            "or place client_secret.json in the project root."
        )

    installed = secret.get("installed", secret.get("web", secret))
    client_id = installed["client_id"]
    client_secret = installed["client_secret"]

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=installed.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    creds.refresh(Request())
    return creds


def upload_short(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy_status: str = "public",
    refresh_token: str | None = None,
) -> str:
    """Upload a video to YouTube as a Short. Returns the video ID.

    If refresh_token is provided, uses it for this upload.
    Otherwise falls back to env var / token file.
    """
    creds = _get_credentials(refresh_token)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response.get("id")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Uploaded: %s", video_url)
    return video_id
