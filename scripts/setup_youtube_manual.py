"""Manual YouTube authentication - paste authorization code from browser.

Use this if automatic browser flow fails with CSRF errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main() -> int:
    print("=" * 70)
    print("YouTube Authentication - Manual Mode")
    print("=" * 70)

    settings = get_settings()
    config_dir = settings.data_dir.parent / "config"
    client_secrets = config_dir / "client_secret.json"
    credentials_file = config_dir / "youtube_credentials.json"

    if not client_secrets.is_file():
        print(f"\n❌ ERROR: Client secrets not found: {client_secrets}")
        return 1

    print(f"\n📂 Using: {client_secrets}")
    print("\n🔐 Starting manual OAuth flow...")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets), 
            SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )

        # Get authorization URL
        auth_url, _ = flow.authorization_url(prompt='consent')

        print("📋 INSTRUCTIONS:")
        print("1. Copy this URL and open it in your browser:")
        print()
        print(auth_url)
        print()
        print("2. Login and click 'Allow'")
        print("3. Copy the authorization code from the browser")
        print("4. Paste it below")
        print()

        # Get code from user
        code = input("Enter authorization code: ").strip()

        if not code:
            print("\n❌ No code provided")
            return 1

        # Exchange code for credentials
        print("\n🔄 Exchanging code for access token...")
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save credentials
        import json
        credentials_file.parent.mkdir(parents=True, exist_ok=True)
        creds_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }
        credentials_file.write_text(json.dumps(creds_data, indent=2), encoding="utf-8")

        print(f"\n✅ SUCCESS!")
        print(f"   Credentials saved to: {credentials_file}")
        print()
        print("🎬 You can now upload videos:")
        print("   python main.py --count 1 --upload")
        print()
        return 0

    except Exception as exc:
        print(f"\n❌ Authentication failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
