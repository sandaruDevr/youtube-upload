import json
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    youtube_client_secret_json: str = ""
    youtube_refresh_token: str = ""
    allowed_user_ids: str = ""
    music_track_filename: str = "music.mp3"
    port: int = 8080
    oauth_redirect_uri: str = "http://localhost:8080/oauth/callback"
    session_secret: str = "change-me-in-production"

    # Firebase config
    firebase_project_id: str = "aces-c8391"
    firebase_db_url: str = "https://aces-c8391-default-rtdb.firebaseio.com"
    firebase_web_api_key: str = "AIzaSyBX8o4tz4huXIjTyGC4qh8r30bq6I8NHD0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def allowed_users(self) -> set[int]:
        if not self.allowed_user_ids.strip():
            return set()
        return {int(uid.strip()) for uid in self.allowed_user_ids.split(",") if uid.strip()}

    @property
    def client_secret_dict(self) -> dict | None:
        if self.youtube_client_secret_json.strip():
            return json.loads(self.youtube_client_secret_json)
        secret_path = Path("client_secret.json")
        if secret_path.exists():
            return json.loads(secret_path.read_text())
        return None

    @property
    def music_path(self) -> Path:
        return Path("assets") / self.music_track_filename


settings = Settings()
