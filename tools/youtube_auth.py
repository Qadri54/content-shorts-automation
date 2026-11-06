"""OAuth2 authentication for YouTube Data API v3."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeAuthError(RuntimeError):
    """Raised when YouTube authentication fails."""


class YouTubeAuth:
    def __init__(self, client_secrets_file: Path, credentials_file: Path) -> None:
        self.client_secrets_file = client_secrets_file
        self.credentials_file = credentials_file
        self._credentials: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        """Get valid credentials, refreshing or re-authenticating as needed."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        if self.credentials_file.is_file():
            try:
                self._credentials = Credentials.from_authorized_user_file(
                    str(self.credentials_file), SCOPES
                )
            except Exception as exc:
                logger.warning("Failed to load saved credentials: %s", exc)
                self._credentials = None

        if self._credentials and self._credentials.expired and self._credentials.refresh_token:
            logger.info("Refreshing expired access token...")
            try:
                self._credentials.refresh(Request())
                self._save_credentials()
                logger.info("Token refreshed successfully")
            except Exception as exc:
                raise YouTubeAuthError(f"Failed to refresh token: {exc}") from exc
        elif not self._credentials or not self._credentials.valid:
            raise YouTubeAuthError(
                "No valid credentials found. Run 'python scripts/setup_youtube.py' first."
            )

        return self._credentials

    def authenticate_new(self) -> Credentials:
        """Run OAuth flow to get new credentials (opens browser)."""
        if not self.client_secrets_file.is_file():
            raise YouTubeAuthError(
                f"Client secrets file not found: {self.client_secrets_file}\n"
                "Download it from Google Cloud Console and save as config/client_secret.json"
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_file), SCOPES
            )
            # Use different port and disable state verification temporarily
            self._credentials = flow.run_local_server(
                port=8090,
                authorization_prompt_message="Opening browser for YouTube authorization...",
                success_message="Authorization complete! You can close this window.",
                open_browser=True,
            )
            self._save_credentials()
            logger.info("Authentication successful! Credentials saved to %s", self.credentials_file)
            return self._credentials
        except Exception as exc:
            raise YouTubeAuthError(f"OAuth flow failed: {exc}") from exc

    def _save_credentials(self) -> None:
        """Save credentials to file."""
        if not self._credentials:
            return
        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        creds_data = {
            "token": self._credentials.token,
            "refresh_token": self._credentials.refresh_token,
            "token_uri": self._credentials.token_uri,
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "scopes": self._credentials.scopes,
        }
        self.credentials_file.write_text(
            json.dumps(creds_data, indent=2), encoding="utf-8"
        )

    def revoke(self) -> None:
        """Revoke credentials and delete saved token."""
        if self._credentials:
            try:
                self._credentials.revoke(Request())
                logger.info("Credentials revoked")
            except Exception as exc:
                logger.warning("Failed to revoke credentials: %s", exc)
        if self.credentials_file.is_file():
            self.credentials_file.unlink()
            logger.info("Credentials file deleted: %s", self.credentials_file)
