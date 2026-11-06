"""Re-upload a locally saved video that failed to upload to YouTube."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from tools.youtube_auth import YouTubeAuth
from tools.youtube_uploader import YouTubeUploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_video_folder(output_dir: Path, query: str) -> Path | None:
    """Find video folder by timestamp or title substring."""
    if not output_dir.exists():
        return None
    
    # Try exact match first
    candidate = output_dir / query
    if candidate.exists() and candidate.is_dir():
        return candidate
    
    # Try substring match on folder names
    for folder in output_dir.iterdir():
        if folder.is_dir() and query.lower() in folder.name.lower():
            return folder
    
    return None


def reupload_video(video_folder: Path) -> None:
    """Re-upload video from a completed output folder."""
    logger.info("Re-uploading from: %s", video_folder.name)
    
    # Find blueprint.json
    blueprint_path = video_folder / "blueprint.json"
    if not blueprint_path.exists():
        raise FileNotFoundError(f"blueprint.json not found in {video_folder}")
    
    with open(blueprint_path, encoding="utf-8") as f:
        blueprint = json.load(f)
    
    # Find video file
    video_files = list(video_folder.glob("*.mp4"))
    if not video_files:
        raise FileNotFoundError(f"No .mp4 file found in {video_folder}")
    video_path = video_files[0]
    
    # Optional files
    thumbnail_path = video_folder / f"{video_path.stem}.png"
    captions_path = video_folder / f"{video_path.stem}.srt"
    
    logger.info("Video: %s", video_path.name)
    logger.info("Title: %s", blueprint["title"])
    logger.info("Thumbnail: %s", "Yes" if thumbnail_path.exists() else "No")
    logger.info("Captions: %s", "Yes" if captions_path.exists() else "No")
    
    # Initialize YouTube uploader
    settings = Settings()
    client_secrets = settings.config_dir / "client_secret.json"
    credentials_file = settings.config_dir / "youtube_credentials.json"
    auth = YouTubeAuth(client_secrets, credentials_file)
    uploader = YouTubeUploader(auth)
    
    # Upload
    result = uploader.upload_video(
        video_path=video_path,
        title=blueprint["title"],
        description=blueprint["description"],
        tags=blueprint.get("tags", []),
        category_id="27",  # Education
        privacy_status="public",
        made_for_kids=False,
        thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        captions_path=captions_path if captions_path.exists() else None,
    )
    
    logger.info("✓ Upload successful!")
    logger.info("  Video ID: %s", result.video_id)
    logger.info("  URL: %s", result.url)
    
    # Save upload result
    upload_result_path = video_folder / "upload_result.json"
    with open(upload_result_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "video_id": result.video_id,
                "url": result.url,
                "title": result.title,
                "privacy_status": result.privacy_status,
                "uploaded_at": result.uploaded_at,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("  Upload result saved: %s", upload_result_path.name)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/reupload_video.py <folder_name_or_substring>")
        print()
        print("Examples:")
        print("  python scripts/reupload_video.py 20261102_000045_terungkap-mengapa-madu-tidak-pernah-basi-selamanya")
        print("  python scripts/reupload_video.py madu")
        print()
        
        # List available folders
        output_dir = Path(__file__).parent.parent / "data" / "output"
        if output_dir.exists():
            folders = [f.name for f in output_dir.iterdir() if f.is_dir()]
            if folders:
                print("Available folders:")
                for folder in sorted(folders)[-5:]:  # Show last 5
                    print(f"  {folder}")
        sys.exit(1)
    
    query = sys.argv[1]
    output_dir = Path(__file__).parent.parent / "data" / "output"
    
    video_folder = find_video_folder(output_dir, query)
    if not video_folder:
        logger.error("Video folder not found: %s", query)
        sys.exit(1)
    
    try:
        reupload_video(video_folder)
    except Exception as exc:
        logger.error("Re-upload failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
