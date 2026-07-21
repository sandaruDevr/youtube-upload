import logging
import secrets

from google_auth_oauthlib.flow import Flow

from .config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_client_config() -> dict:
    secret = settings.client_secret_dict
    if not secret:
        raise RuntimeError(
            "No YouTube client secret found. Set YOUTUBE_CLIENT_SECRET_JSON env var "
            "or place client_secret.json in the project root."
        )
    return secret


def create_oauth_flow(state: str | None = None) -> Flow:
    """Create an OAuth Flow configured for web server flow."""
    client_config = _get_client_config()
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.oauth_redirect_uri,
        state=state,
    )
    return flow


def get_authorization_url(state: str) -> tuple[str, str]:
    """Generate the Google OAuth authorization URL.

    Uses access_type=offline and prompt=consent to ensure we get a refresh token.
    """
    flow = create_oauth_flow(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )
    return auth_url


def exchange_code_for_tokens(code: str, state: str) -> dict:
    """Exchange the OAuth authorization code for tokens.

    Returns dict with refresh_token, access_token, expiry, and client info.
    """
    flow = create_oauth_flow(state=state)
    flow.fetch_token(code=code)

    credentials = flow.credentials

    client_config = _get_client_config()
    installed = client_config.get("installed", client_config.get("web", client_config))

    return {
        "refresh_token": credentials.refresh_token,
        "access_token": credentials.token,
        "expiry": credentials.expiry.timestamp() if credentials.expiry else None,
        "client_id": installed["client_id"],
        "client_secret": installed["client_secret"],
        "token_uri": installed.get("token_uri", "https://oauth2.googleapis.com/token"),
    }


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)
