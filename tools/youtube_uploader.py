"""YouTube Data API v3 uploader: video, thumbnail, captions, metadata."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from tools.youtube_auth import YouTubeAuth

logger = logging.getLogger(__name__)


class YouTubeUploadError(RuntimeError):
    """Raised when YouTube upload fails."""


@dataclass
class UploadResult:
    video_id: str
    url: str
    title: str
    privacy_status: str
    uploaded_at: str


class YouTubeUploader:
    MAX_RETRIES = 3
    RETRY_DELAY = 5.0

    def __init__(self, auth: YouTubeAuth) -> None:
        self.auth = auth
        self._service = None

    def _get_service(self):
        """Get or create YouTube API service."""
        if self._service is None:
            credentials = self.auth.get_credentials()
            self._service = build("youtube", "v3", credentials=credentials)
        return self._service

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: str = "27",
        privacy_status: str = "public",
        made_for_kids: bool = False,
        thumbnail_path: Optional[Path] = None,
        captions_path: Optional[Path] = None,
    ) -> UploadResult:
        """Upload a video with metadata, thumbnail, and captions."""
        if not video_path.is_file():
            raise YouTubeUploadError(f"Video file not found: {video_path}")

        logger.info("Uploading video: %s", video_path.name)
        logger.info("  Title: %s", title)
        logger.info("  Privacy: %s", privacy_status)

        # Step 1: Upload video
        video_id = self._upload_video_file(
            video_path, title, description, tags, category_id, privacy_status, made_for_kids
        )
        logger.info("  Video uploaded: %s", video_id)

        # Step 2: Set thumbnail
        if thumbnail_path and thumbnail_path.is_file():
            self._set_thumbnail(video_id, thumbnail_path)
            logger.info("  Thumbnail set: %s", thumbnail_path.name)
        else:
            logger.warning("  Thumbnail not found, skipping: %s", thumbnail_path)

        # Step 3: Upload captions
        if captions_path and captions_path.is_file():
            self._upload_captions(video_id, captions_path)
            logger.info("  Captions uploaded: %s", captions_path.name)
        else:
            logger.warning("  Captions not found, skipping: %s", captions_path)

        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("  YouTube URL: %s", url)

        return UploadResult(
            video_id=video_id,
            url=url,
            title=title,
            privacy_status=privacy_status,
            uploaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _upload_video_file(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
        made_for_kids: bool,
    ) -> str:
        """Upload the video file and return video_id."""
        service = self._get_service()

        body = {
            "snippet": {
                "title": title[:100],  # YouTube max 100 chars
                "description": description[:5000],  # YouTube max 5000 chars
                "tags": tags[:500] if isinstance(tags, list) else [],
                "categoryId": category_id,
                "defaultLanguage": "id",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                request = service.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media,
                )
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.info("    Upload progress: %d%%", progress)

                return response["id"]

            except HttpError as exc:
                if exc.resp.status in {500, 502, 503, 504} and attempt < self.MAX_RETRIES:
                    logger.warning("    Upload failed (attempt %d/%d): %s", attempt, self.MAX_RETRIES, exc)
                    time.sleep(self.RETRY_DELAY * attempt)
                    media.stream().seek(0)  # Reset stream for retry
                else:
                    raise YouTubeUploadError(f"Video upload failed: {exc}") from exc

            except (OSError, ConnectionError, TimeoutError) as exc:
                # Handle connection aborts, socket errors (WinError 10053, etc.)
                if attempt < self.MAX_RETRIES:
                    logger.warning("    Connection error (attempt %d/%d): %s", attempt, self.MAX_RETRIES, exc)
                    time.sleep(self.RETRY_DELAY * attempt)
                    # Recreate media object with fresh file handle
                    media = MediaFileUpload(
                        str(video_path),
                        mimetype="video/mp4",
                        resumable=True,
                        chunksize=10 * 1024 * 1024,
                    )
                else:
                    raise YouTubeUploadError(f"Video upload failed after connection errors: {exc}") from exc

        raise YouTubeUploadError("Video upload failed after all retries")

    def _set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        """Set custom thumbnail for a video."""
        service = self._get_service()
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/png")

        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()
        except HttpError as exc:
            logger.error("Failed to set thumbnail: %s", exc)
            # Don't raise - thumbnail is optional

    def _upload_captions(self, video_id: str, captions_path: Path, language: str = "id") -> None:
        """Upload SRT captions for a video."""
        service = self._get_service()

        body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": "Indonesian",
                "isDraft": False,
            }
        }

        for attempt in range(1, self.MAX_RETRIES + 1):
            media = MediaFileUpload(
                str(captions_path),
                mimetype="application/octet-stream",
                resumable=True,
            )

            try:
                service.captions().insert(
                    part="snippet",
                    body=body,
                    media_body=media,
                ).execute()
                return  # Success

            except HttpError as exc:
                logger.error("Failed to upload captions (attempt %d/%d): %s", attempt, self.MAX_RETRIES, exc)
                if attempt >= self.MAX_RETRIES:
                    # Don't raise - captions are optional
                    return
                time.sleep(self.RETRY_DELAY * attempt)

            except (OSError, ConnectionError, TimeoutError) as exc:
                logger.warning("Caption upload connection error (attempt %d/%d): %s", attempt, self.MAX_RETRIES, exc)
                if attempt >= self.MAX_RETRIES:
                    logger.error("Captions upload failed after retries - skipping")
                    return
                time.sleep(self.RETRY_DELAY * attempt)

    def delete_video(self, video_id: str) -> None:
        """Delete a video from YouTube."""
        service = self._get_service()
        try:
            service.videos().delete(id=video_id).execute()
            logger.info("Video deleted: %s", video_id)
        except HttpError as exc:
            raise YouTubeUploadError(f"Failed to delete video: {exc}") from exc

    def get_video_status(self, video_id: str) -> dict:
        """Get video processing status and metadata."""
        service = self._get_service()
        try:
            response = service.videos().list(
                part="status,snippet,contentDetails",
                id=video_id,
            ).execute()

            if not response.get("items"):
                raise YouTubeUploadError(f"Video not found: {video_id}")

            return response["items"][0]
        except HttpError as exc:
            raise YouTubeUploadError(f"Failed to get video status: {exc}") from exc
