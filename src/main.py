import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telegram.ext import Application

from .config import settings
from .telegram_bot import build_application
from .web.routes import router as web_router
from .token_store import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Telegram bot (optional — only starts if token is configured)
bot_app: Application | None = None
if settings.telegram_bot_token:
    bot_app = build_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    logger.info("Token database initialized")

    if bot_app:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started polling")
    else:
        logger.info("No TELEGRAM_BOT_TOKEN set — Telegram bot disabled")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


app = FastAPI(title="YouTube Shorts Uploader", lifespan=lifespan)

# Mount web routes (OAuth, dashboard, upload API)
app.include_router(web_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, log_level="info")
