import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..token_store import verify_firebase_token, get_refresh_token, delete_refresh_token
from ..oauth_manager import get_authorization_url, exchange_code_for_tokens
from ..video_processor import process_video, process_image, TEMP_DIR
from ..youtube_uploader import upload_short

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")

TEMP_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_uid_from_request(request: Request) -> str | None:
    """Extract and verify Firebase ID token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    id_token_str = auth_header.split(" ", 1)[1]
    decoded = await verify_firebase_token(id_token_str)
    if not decoded:
        return None
    return decoded.get("uid") or decoded.get("sub")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ---------------------------------------------------------------------------
# YouTube OAuth — initiate and callback
# ---------------------------------------------------------------------------

@router.get("/api/youtube/auth-url")
async def youtube_auth_url(request: Request):
    """Return the YouTube OAuth URL for the authenticated user."""
    uid = await _get_uid_from_request(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_url = get_authorization_url(state=uid)
    return JSONResponse({"auth_url": auth_url})


@router.get("/oauth/callback")
async def oauth_callback(request: Request):
    """YouTube OAuth callback — exchange code for tokens, redirect to frontend with token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"OAuth error: {error}"},
        )

    if not code or not state:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Missing code or state in OAuth callback."},
        )

    try:
        token_info = exchange_code_for_tokens(code=code, state=state)
        refresh_token = token_info["refresh_token"]
        if not refresh_token:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "No refresh token returned. You may have already connected this account. Try disconnecting and reconnecting."},
            )
        # Redirect to frontend with UID and refresh token — frontend stores it in Firebase DB
        redirect = f"/dashboard?yt_uid={state}&yt_refresh_token={refresh_token}"
        return RedirectResponse(url=redirect, status_code=302)
    except Exception as e:
        logger.exception("OAuth token exchange failed")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
        )


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _process_and_queue(
    input_path: Path,
    output_path: Path,
    is_image: bool,
    refresh_token: str,
):
    """Process a single file and publish to YouTube. Runs in background."""
    try:
        if is_image:
            process_image(input_path, output_path)
        else:
            process_video(input_path, output_path)

        upload_short(output_path, "Short", "", [], "public", refresh_token)
        logger.info("Published file: %s", input_path.name)
    except Exception:
        logger.exception("Failed to process/publish %s", input_path)
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_SIZE = 50 * 1024 * 1024  # 50MB


# ---------------------------------------------------------------------------
# Upload API
# ---------------------------------------------------------------------------

@router.post("/api/upload")
async def api_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    uid = await _get_uid_from_request(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get Firebase ID token for DB access
    auth_header = request.headers.get("Authorization", "")
    id_token_str = auth_header.split(" ", 1)[1]

    refresh_token = await get_refresh_token(uid, id_token_str)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="YouTube account not connected")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    saved_files: list[tuple[Path, Path, bool]] = []

    try:
        for file in files:
            if not file.filename:
                continue

            ext = Path(file.filename).suffix.lower()
            input_path = TEMP_DIR / f"web_input_{uuid.uuid4().hex}{ext}"
            output_path = TEMP_DIR / f"web_short_{uuid.uuid4().hex}.mp4"
            is_image = ext in IMAGE_EXTS

            size = 0
            with open(input_path, "wb") as f:
                while chunk := await file.read(8192):
                    size += len(chunk)
                    if size > MAX_SIZE:
                        raise HTTPException(status_code=413, detail=f"File too large (max 50MB): {file.filename}")
                    f.write(chunk)

            saved_files.append((input_path, output_path, is_image))

        if not saved_files:
            raise HTTPException(status_code=400, detail="No valid files provided")

        for input_path, output_path, is_image in saved_files:
            background_tasks.add_task(
                _process_and_queue,
                input_path,
                output_path,
                is_image,
                refresh_token,
            )

        return JSONResponse({
            "success": True,
            "queued": True,
            "count": len(saved_files),
            "message": f"{len(saved_files)} file(s) submitted to the publishing queue. They will be processed and published to your YouTube channel shortly.",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Web upload failed: %s", str(e))
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Status & Disconnect
# ---------------------------------------------------------------------------

@router.get("/api/status")
async def api_status(request: Request):
    uid = await _get_uid_from_request(request)
    if not uid:
        return {"connected": False}

    auth_header = request.headers.get("Authorization", "")
    id_token_str = auth_header.split(" ", 1)[1]

    refresh_token = await get_refresh_token(uid, id_token_str)
    if not refresh_token:
        return {"connected": False}

    return {"connected": True}


@router.post("/api/disconnect")
async def api_disconnect(request: Request):
    uid = await _get_uid_from_request(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_header = request.headers.get("Authorization", "")
    id_token_str = auth_header.split(" ", 1)[1]

    success = await delete_refresh_token(uid, id_token_str)
    return JSONResponse({"success": success})
