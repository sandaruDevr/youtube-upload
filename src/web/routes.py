import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..token_store import store_token, get_token, delete_token
from ..oauth_manager import get_authorization_url, exchange_code_for_tokens, generate_session_id
from ..video_processor import process_video, process_image, TEMP_DIR
from ..youtube_uploader import upload_short

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")

TEMP_DIR.mkdir(exist_ok=True)


def _get_session_id(request: Request) -> str | None:
    return request.cookies.get("yt_session")


def _set_session_cookie(response, session_id: str):
    response.set_cookie(
        "yt_session",
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session_id = _get_session_id(request)
    token_data = None
    if session_id:
        token_data = await get_token(session_id)

    if token_data:
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/login")
async def login(request: Request):
    session_id = _get_session_id(request)
    if not session_id:
        session_id = generate_session_id()

    auth_url = get_authorization_url(state=session_id)
    response = RedirectResponse(url=auth_url)
    _set_session_cookie(response, session_id)
    return response


@router.get("/oauth/callback")
async def oauth_callback(request: Request):
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

    session_id = _get_session_id(request)
    logger.info("OAuth callback - state=%s, session_id=%s, cookies=%s", state, session_id, dict(request.cookies))
    if not session_id or session_id != state:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Session mismatch. Please try connecting again."},
        )

    try:
        token_info = exchange_code_for_tokens(code=code, state=state)
        await store_token(
            session_id=session_id,
            refresh_token=token_info["refresh_token"],
            access_token=token_info["access_token"],
            expiry=token_info["expiry"],
            client_id=token_info["client_id"],
            client_secret=token_info["client_secret"],
            token_uri=token_info["token_uri"],
        )
        return RedirectResponse(url="/dashboard", status_code=302)
    except Exception as e:
        logger.exception("OAuth token exchange failed")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
        )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session_id = _get_session_id(request)
    if not session_id:
        return RedirectResponse(url="/", status_code=302)

    token_data = await get_token(session_id)
    if not token_data:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "connected": True,
            "channel_title": token_data.get("channel_title") or "YouTube Account",
        },
    )


@router.post("/api/upload")
async def api_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy: str = Form("public"),
):
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_data = await get_token(session_id)
    if not token_data:
        raise HTTPException(status_code=401, detail="YouTube account not connected")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    input_path = TEMP_DIR / f"web_input_{uuid.uuid4().hex}{ext}"
    output_path = TEMP_DIR / f"web_short_{uuid.uuid4().hex}.mp4"

    try:
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)

        if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            await asyncio.to_thread(process_image, input_path, output_path)
        else:
            await asyncio.to_thread(process_video, input_path, output_path)

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        video_id = await asyncio.to_thread(
            upload_short,
            output_path,
            title,
            description,
            tag_list,
            privacy,
            token_data["refresh_token"],
        )

        return JSONResponse({
            "success": True,
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    except Exception as e:
        logger.exception("Web upload failed")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/api/disconnect")
async def api_disconnect(request: Request):
    session_id = _get_session_id(request)
    if session_id:
        await delete_token(session_id)
    response = JSONResponse({"success": True})
    response.delete_cookie("yt_session")
    return response


@router.get("/api/status")
async def api_status(request: Request):
    session_id = _get_session_id(request)
    if not session_id:
        return {"connected": False}
    token_data = await get_token(session_id)
    if not token_data:
        return {"connected": False}
    return {
        "connected": True,
        "channel_title": token_data.get("channel_title") or "YouTube Account",
    }
