"""First-time YouTube authentication setup script.

Run this once to authenticate with your YouTube account.
Opens browser for OAuth flow and saves credentials locally.

Usage:
    python scripts/setup_youtube.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from tools.youtube_auth import YouTubeAuth, YouTubeAuthError


def main() -> int:
    print("=" * 70)
    print("YouTube Authentication Setup")
    print("=" * 70)

    settings = get_settings()
    config_dir = settings.data_dir.parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    client_secrets = config_dir / "client_secret.json"
    credentials_file = config_dir / "youtube_credentials.json"

    # Check if client_secret.json exists
    if not client_secrets.is_file():
        print(f"\n❌ ERROR: Client secrets file not found!")
        print(f"   Expected location: {client_secrets}")
        print()
        print("📝 SETUP INSTRUCTIONS:")
        print("   1. Go to: https://console.cloud.google.com")
        print("   2. Create a new project (or select existing)")
        print("   3. Enable 'YouTube Data API v3'")
        print("   4. Go to: Credentials → Create Credentials → OAuth Client ID")
        print("   5. Application type: Desktop app")
        print("   6. Download JSON and save it as:")
        print(f"      {client_secrets}")
        print()
        return 1

    # Check if already authenticated
    if credentials_file.is_file():
        print(f"\n✓ Found existing credentials: {credentials_file}")
        response = input("Re-authenticate? (y/N): ").strip().lower()
        if response != "y":
            print("Setup cancelled.")
            return 0

    # Run OAuth flow
    print(f"\n📂 Using client secrets: {client_secrets}")
    print("\n🔐 Starting OAuth flow...")
    print("   → Browser will open for authorization")
    print("   → Login with your YouTube account")
    print("   → Click 'Allow' when prompted")
    print()

    auth = YouTubeAuth(client_secrets, credentials_file)

    try:
        credentials = auth.authenticate_new()
        print("\n✅ SUCCESS!")
        print(f"   Credentials saved to: {credentials_file}")
        print()
        print("🎬 You can now upload videos:")
        print("   python main.py --count 1 --upload")
        print()
        return 0

    except YouTubeAuthError as exc:
        print(f"\n❌ Authentication failed: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        return 130
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
