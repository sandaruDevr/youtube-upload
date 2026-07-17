import logging
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from .config import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

logger = logging.getLogger(__name__)


def run_oauth_flow() -> None:
    """Run local OAuth flow to obtain a refresh token.

    Run this locally (not on Railway) with your client_secret.json in place:
        python -m src.oauth_setup
    """
    secret = settings.client_secret_dict
    if not secret:
        raise RuntimeError(
            "No client secret found. Place client_secret.json in the project root "
            "or set YOUTUBE_CLIENT_SECRET_JSON env var."
        )

    import json
    secret_path = Path("client_secret.json")
    if not secret_path.exists():
        secret_path.write_text(json.dumps(secret))

    # InstalledAppFlow works with "installed" type credentials
    # For "web" type, we need to use Flow with a fixed redirect URI
    credential_type = "installed" if "installed" in secret else "web"

    if credential_type == "installed":
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        creds = flow.run_local_server(port=0)
    else:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            str(secret_path),
            scopes=SCOPES,
            redirect_uri="http://localhost:8080/oauth/callback",
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        print(f"\nOpen this URL in your browser:\n{auth_url}\n")
        code = input("Enter the authorization code: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials

    token_data = {
        "refresh_token": creds.refresh_token,
        "token": creds.token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }

    Path("token.json").write_text(json.dumps(token_data, indent=2))
    print("\n=== OAuth Setup Complete ===")
    print(f"Refresh token: {creds.refresh_token}")
    print("Set this as YOUTUBE_REFRESH_TOKEN in your .env or Railway env vars.")
    print("token.json has been saved for local use.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_oauth_flow()
