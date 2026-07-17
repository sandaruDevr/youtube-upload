# YouTube Shorts Uploader

Upload videos/images as YouTube Shorts via a **web UI** or **Telegram bot**. Automatically formats media to 1080×1920 vertical, adds background music, and publishes to YouTube using OAuth refresh tokens that don't expire.

## Features

- **Web UI**: Connect your YouTube account via Google OAuth, upload media from browser
- **Telegram Bot**: Send media with caption, auto-uploads as a Short
- **ffmpeg processing**: Scales to 1080×1920, trims to ≤60s, replaces audio with your music track
- **Refresh tokens**: Stored in SQLite — stays connected indefinitely (no 1-hour expiry)
- **Railway-ready**: Dockerfile included, deploy in minutes

## Prerequisites

- Python 3.12+
- `ffmpeg` installed locally
- A Google Cloud project with YouTube Data API v3 enabled

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get YouTube OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project, enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials — **Web application** type (for web UI flow)
4. Add authorized redirect URIs:
   - `http://localhost:8080/oauth/callback` (local)
   - `https://your-app.up.railway.app/oauth/callback` (Railway)
5. Download `client_secret.json` and place it in the project root

### 3. Add your music track

Place your music file at `assets/music.mp3` (or update `MUSIC_TRACK_FILENAME` in `.env`).

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
- `YOUTUBE_CLIENT_SECRET_JSON` — paste entire `client_secret.json` content as one line (or keep the file in root)
- `OAUTH_REDIRECT_URI` — must match what's in Google Cloud Console
- `SESSION_SECRET` — random string for cookie signing
- `TELEGRAM_BOT_TOKEN` — from BotFather (optional, leave empty to disable Telegram)
- `YOUTUBE_REFRESH_TOKEN` — only needed for Telegram bot (web UI stores tokens in DB)
- `ALLOWED_USER_IDS` — comma-separated Telegram user IDs (optional)

### 5. Run locally

```bash
python -m src.main
```

Open `http://localhost:8080` in your browser → click **Connect YouTube Account** → authorize → upload Shorts.

### 6. (Optional) Get refresh token for Telegram bot

If you want to use the Telegram bot (which runs headless without web OAuth), get a refresh token:

```bash
python -m src.oauth_setup
```

Set the printed refresh token as `YOUTUBE_REFRESH_TOKEN` in `.env`.

## Deploy to Railway

1. Push this repo to GitHub
2. Go to [Railway](https://railway.app) → New Project → Deploy from GitHub repo
3. Railway will detect the `Dockerfile` automatically
4. Add environment variables in Railway dashboard:
   - `YOUTUBE_CLIENT_SECRET_JSON` — paste client_secret.json content
   - `OAUTH_REDIRECT_URI` — `https://your-app.up.railway.app/oauth/callback`
   - `SESSION_SECRET` — random string
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `YOUTUBE_REFRESH_TOKEN` (only for Telegram bot)
   - `MUSIC_TRACK_FILENAME` (default: `music.mp3`)
5. Deploy
6. Open your Railway URL → connect YouTube → start uploading

**Note:** The music track file needs to be committed to the repo in `assets/` since Railway doesn't have persistent file storage. Remove `assets/music.*` from `.gitignore` to commit it.

**Note:** Railway's filesystem is ephemeral. The SQLite DB will reset on redeploy. For production, use Railway's PostgreSQL add-on (future enhancement) or the Telegram bot mode with `YOUTUBE_REFRESH_TOKEN` env var.

## Deploy to Render

1. Push this repo to GitHub
2. Go to [Render](https://render.com) → New → Web Service → Connect your GitHub repo
3. Render will detect the `Dockerfile` automatically (or use `render.yaml` for blueprint deploy)
4. **Add a PostgreSQL database** (free tier available) — Render will auto-set `DATABASE_URL` env var
5. Set environment variables in Render dashboard:
   - `YOUTUBE_CLIENT_SECRET_JSON` — paste client_secret.json content
   - `OAUTH_REDIRECT_URI` — `https://your-app.onrender.com/oauth/callback`
   - `SESSION_SECRET` — random string
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `YOUTUBE_REFRESH_TOKEN` (only for Telegram bot)
   - `MUSIC_TRACK_FILENAME` (default: `music.mp3`)
6. Deploy
7. Open your Render URL → connect YouTube → start uploading

**Important for Google OAuth:** Add `https://your-app.onrender.com/oauth/callback` to authorized redirect URIs in Google Cloud Console.

**Note:** The music track file needs to be committed to the repo in `assets/`. Remove `assets/music.*` from `.gitignore` to commit it.

**Note:** Render's free tier spins down after inactivity. With PostgreSQL, tokens persist across restarts. Without PostgreSQL (SQLite), tokens are lost on service restart.

## Usage

### Web UI
1. Open the app URL in your browser
2. Click **Connect YouTube Account** → authorize with Google
3. Upload a video/image with title, description, tags, and privacy setting
4. Get the YouTube URL back instantly

### Telegram Bot
1. Open your bot in Telegram
2. Send `/start` to verify it's running
3. Send a video or image **with a caption** — the caption becomes the YouTube title
4. Wait for processing + upload confirmation

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── config.py             # Environment & settings
│   ├── main.py               # FastAPI server + bot startup
│   ├── telegram_bot.py       # Telegram handlers (optional)
│   ├── video_processor.py    # ffmpeg processing (Shorts format)
│   ├── youtube_uploader.py   # YouTube Data API upload
│   ├── oauth_manager.py      # Web OAuth flow (authorization URL + token exchange)
│   ├── oauth_setup.py        # CLI OAuth flow for Telegram bot refresh token
│   ├── token_store.py        # SQLite token storage (refresh tokens)
│   └── web/
│       ├── __init__.py
│       ├── routes.py         # Web routes (index, login, callback, dashboard, upload API)
│       └── templates/
│           ├── base.html     # Base template with TailwindCSS
│           ├── index.html    # Landing page with "Connect YouTube" button
│           ├── dashboard.html # Upload form + status
│           └── error.html    # Error display
├── assets/
│   └── music.mp3             # Your background music track
├── Dockerfile
├── Procfile
├── railway.toml
├── requirements.txt
└── .env.example
```

## How OAuth Works

1. User clicks **Connect YouTube Account** → redirected to Google consent screen
2. Google redirects back to `/oauth/callback` with an authorization code
3. Server exchanges code for `refresh_token` + `access_token`
4. `refresh_token` is stored in SQLite DB (per-session)
5. On each upload, `refresh_token` is used to get a fresh `access_token` (auto-refresh)
6. **The refresh token does not expire** — user stays connected indefinitely

## Notes

- Videos are trimmed to 60 seconds max (YouTube Shorts limit)
- Images are converted to 30-second videos with the music track
- If no music track is found, original audio is kept (for videos) or silent audio is generated (for images)
- All temp files are cleaned up after processing
