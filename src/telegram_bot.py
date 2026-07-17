import asyncio
import logging
import uuid
from pathlib import Path

from telegram import Update, Message
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import settings
from .video_processor import process_video, process_image, TEMP_DIR
from .youtube_uploader import upload_short

logger = logging.getLogger(__name__)


def _is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_users
    if not allowed:
        return True
    return user_id in allowed


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎬 **YouTube Shorts Bot**\n\n"
        "Send me a video or image with a caption and I'll upload it to YouTube as a Short!\n\n"
        "Commands:\n"
        "/start - Show this help\n"
        "/cancel - Clear pending uploads\n\n"
        "Just send media with caption text — that caption becomes the YouTube title."
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("✅ Nothing to cancel. Just send media with a caption to upload.")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    msg = update.message
    caption = (msg.caption or "").strip()
    if not caption:
        await msg.reply_text(
            "⚠️ Please add a caption with the media — it becomes the YouTube title.\n"
            "Send the media again with a caption."
        )
        return

    status_msg = await msg.reply_text("📥 Downloading media...")

    file_path: Path | None = None
    output_path = TEMP_DIR / f"short_{uuid.uuid4().hex}.mp4"

    try:
        file_path = await _download_media(msg, context)
        if not file_path:
            await status_msg.edit_text("❌ Could not download media. Unsupported type.")
            return

        await status_msg.edit_text("🎬 Processing into YouTube Shorts format...")

        if file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            await asyncio.to_thread(process_image, file_path, output_path)
        else:
            await asyncio.to_thread(process_video, file_path, output_path)

        await status_msg.edit_text("📤 Uploading to YouTube...")

        video_id = await asyncio.to_thread(upload_short, output_path, caption)
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        await status_msg.edit_text(
            f"✅ Uploaded successfully!\n\n"
            f"Title: {caption}\n"
            f"URL: {video_url}"
        )

    except Exception as e:
        logger.exception("Upload failed")
        await status_msg.edit_text(f"❌ Upload failed: {e}")
    finally:
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)
        if output_path.exists():
            output_path.unlink(missing_ok=True)


async def _download_media(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> Path | None:
    """Download the largest available media file from a Telegram message."""
    tg_file = None
    ext = ".mp4"

    if msg.video:
        tg_file = await msg.video.get_file()
        ext = ".mp4"
    elif msg.photo:
        # Get largest photo
        tg_file = await msg.photo[-1].get_file()
        ext = ".jpg"
    elif msg.document:
        tg_file = await msg.document.get_file()
        mime = msg.document.mime_type or ""
        if "image" in mime:
            ext = ".jpg"
        elif "video" in mime:
            ext = ".mp4"
        else:
            return None
    elif msg.animation:
        tg_file = await msg.animation.get_file()
        ext = ".mp4"
    else:
        return None

    download_path = TEMP_DIR / f"input_{uuid.uuid4().hex}{ext}"
    await tg_file.download_to_drive(str(download_path))
    return download_path


def build_application() -> Application:
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    media_filter = (
        filters.VIDEO
        | filters.PHOTO
        | filters.Document.VIDEO
        | filters.Document.IMAGE
        | filters.ANIMATION
    )
    app.add_handler(MessageHandler(media_filter & filters.CAPTION, handle_media))

    return app
