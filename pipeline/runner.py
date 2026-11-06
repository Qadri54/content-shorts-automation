"""Sequential orchestrator: CrewAI blueprint -> voiceover -> B-roll -> subtitles -> render -> thumbnail -> upload."""

from __future__ import annotations

import json
import logging
import shutil
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import RunPaths, Settings, slugify
from crews.content_crew import ContentCrew, ContentPackage
from pipeline.history import HistoryStore
from schemas.blueprint import VideoBlueprint
from schemas.channel import ChannelProfile
from tools.audio_generator import AudioGenerator
from tools.music_selector import MusicChoice, MusicSelector
from tools.pexels_downloader import ClipResult, PexelsDownloader
from tools.pixabay_downloader import PixabayDownloader
from tools.subtitle_generator import SubtitleGenerator
from tools.thumbnail_generator import ThumbnailGenerator
from tools.video_composer import VideoComposer
from tools.youtube_auth import YouTubeAuth, YouTubeAuthError
from tools.youtube_uploader import YouTubeUploader, UploadResult

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    index: int
    success: bool
    title: str = ""
    output: Optional[Path] = None
    error: str = ""
    elapsed: float = 0.0


class ShortsFactory:
    def __init__(self, settings: Settings, channel: ChannelProfile, verbose: bool = False) -> None:
        self.settings = settings
        self.channel = channel
        self.crew = ContentCrew(settings, channel, verbose=verbose)
        self.audio = AudioGenerator(settings, voice=channel.voice)
        if settings.pixabay_api_key and not settings._is_missing(settings.pixabay_api_key):
            self.video_downloader = PixabayDownloader(settings.pixabay_api_key, settings.video_width, settings.video_height)
            self.stock_source_name = "Pixabay"
        else:
            self.video_downloader = PexelsDownloader(settings.pexels_api_key, settings.video_width, settings.video_height)
            self.stock_source_name = "Pexels"
        self.subtitles = SubtitleGenerator(settings)
        self.composer = VideoComposer(settings)
        self.thumbnail = ThumbnailGenerator(settings)
        self.music = MusicSelector(settings.music_dir)
        self.history = HistoryStore(settings.history_file)
        
        # YouTube uploader (lazy init)
        self._youtube_uploader: Optional[YouTubeUploader] = None

    def _get_youtube_uploader(self) -> YouTubeUploader:
        """Lazy init YouTube uploader only when needed."""
        if self._youtube_uploader is None:
            client_secrets = self.settings.config_dir / "client_secret.json"
            credentials_file = self.settings.config_dir / "youtube_credentials.json"
            auth = YouTubeAuth(client_secrets, credentials_file)
            self._youtube_uploader = YouTubeUploader(auth)
        return self._youtube_uploader

    # ------------------------------------------------------------------ batch
    def run_batch(
        self, count: int, sub_theme_name: Optional[str] = None, blueprint_only: bool = False, 
        cleanup: bool = False, upload: bool = False, upload_private: bool = False
    ) -> List[RunResult]:
        results: List[RunResult] = []
        for index in range(1, count + 1):
            results.append(self._run_safe(index, count, sub_theme_name, blueprint_only, cleanup, upload, upload_private))
            if index < count:
                logger.info("Jeda %.0f detik untuk menjaga rate limit Gemini Free Tier...", self.settings.delay_between_runs)
                time.sleep(self.settings.delay_between_runs)
        return results

    def _run_safe(self, index: int, total: int, sub_theme_name: Optional[str], blueprint_only: bool, 
                  cleanup: bool, upload: bool, upload_private: bool) -> RunResult:
        started = time.monotonic()
        logger.info("=" * 70)
        logger.info("[Video %d/%d] Mulai produksi", index, total)
        try:
            title, output = self.produce(index, total, sub_theme_name, blueprint_only, cleanup, upload, upload_private)
            elapsed = time.monotonic() - started
            logger.info("[Video %d/%d] SELESAI dalam %.0f detik -> %s", index, total, elapsed, output)
            return RunResult(index=index, success=True, title=title, output=output, elapsed=elapsed)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - one failed video must not stop the batch
            elapsed = time.monotonic() - started
            logger.error("[Video %d/%d] GAGAL: %s", index, total, exc)
            logger.debug(traceback.format_exc())
            return RunResult(index=index, success=False, error=str(exc).splitlines()[0], elapsed=elapsed)

    # ------------------------------------------------------------- single run
    def produce(
        self, index: int, total: int, sub_theme_name: Optional[str], blueprint_only: bool, 
        cleanup: bool, upload: bool, upload_private: bool
    ) -> tuple[str, Path]:
        tag = f"[Video {index}/{total}]"
        sub_theme = self.channel.find_sub_theme(sub_theme_name) if sub_theme_name else self.history.pick_sub_theme(self.channel)
        avoid = self.history.recent_topics(sub_theme=sub_theme.name)

        logger.info("%s [1/7] Membuat blueprint (sub-tema: %s)", tag, sub_theme.name)
        package = self.crew.generate(sub_theme, avoid)
        blueprint = package.blueprint
        paths = self.settings.create_run_paths(slugify(blueprint.title)).create()
        self._save_json(paths.blueprint_file, blueprint.model_dump())
        self._save_json(paths.factcheck_file, {
            "draft": package.draft.model_dump(),
            "fact_check": package.fact_check.model_dump(),
            "hook_style": package.hook_style,
            "attempts": package.attempts,
        })

        if blueprint_only:
            description = self._compose_description(blueprint.description, None)
            self._write_metadata(paths, package, description, None, None)
            self._record_history(package, paths.root, None, status="blueprint_only")
            return blueprint.title, paths.root

        logger.info("%s [2/7] Membuat voiceover (%s)", tag, self.audio.voice)
        voice = self.audio.generate(blueprint.scenes, paths.audio_dir)
        durations = [item.duration for item in voice.scenes]

        logger.info("%s [3/7] Mengambil B-roll dari %s (%d scene, STRICT VISUAL)", tag, self.stock_source_name, len(blueprint.scenes))
        fallback = list(sub_theme.fallback_keywords) or [blueprint.topic]
        topic_context = f"{blueprint.sub_theme} {blueprint.topic}"
        clips = self.video_downloader.fetch_for_scenes(
            blueprint.scenes, durations, paths.clips_dir, fallback, topic_context=topic_context
        )
        self._save_json(paths.clips_dir / "clips.json", [self._clip_dict(c) for c in clips])

        logger.info("%s [4/7] Membuat subtitle word-level (faster-whisper)", tag)
        self.subtitles.generate(voice.scenes, paths.ass_file, paths.srt_file)

        logger.info("%s [5/7] Merakit & merender video final", tag)
        music = self.music.select(blueprint.music_mood, self.history.recent_music())
        if music:
            logger.info("      Musik: %s (mood %s)", music.relative, music.mood)
        else:
            logger.info("      Folder data/music kosong -> video dirender tanpa musik latar")
        self.composer.compose(
            clips=clips,
            scene_durations=durations,
            voiceover=voice.voiceover_path,
            subtitles=paths.ass_file,
            music=music.path if music else None,
            scenes_dir=paths.scenes_dir,
            output=paths.final_video,
        )

        logger.info("%s [6/7] Membuat thumbnail", tag)
        try:
            self.thumbnail.generate(blueprint, paths.final_video, paths.thumbnail_file)
        except Exception as exc:
            logger.error("Thumbnail generation failed: %s", exc)
            logger.warning("Continuing without thumbnail (video will use auto-generated YouTube thumbnail)...")

        description = self._compose_description(blueprint.description, music)
        self._write_metadata(paths, package, description, music, voice.total_duration)
        self._record_history(package, paths.final_video, music, status="rendered")

        # Step 7: Upload to YouTube (optional)
        if upload or upload_private:
            logger.info("%s [7/7] Uploading ke YouTube", tag)
            try:
                upload_result = self._upload_to_youtube(
                    paths, 
                    blueprint, 
                    description, 
                    privacy="private" if upload_private else self.settings.youtube_default_privacy
                )
                self._save_json(paths.upload_result_file, {
                    "video_id": upload_result.video_id,
                    "url": upload_result.url,
                    "title": upload_result.title,
                    "privacy_status": upload_result.privacy_status,
                    "uploaded_at": upload_result.uploaded_at,
                })
                logger.info("      ✓ Video uploaded: %s", upload_result.url)
                logger.info("      ✓ Status: %s", upload_result.privacy_status)
            except YouTubeAuthError as exc:
                logger.error("YouTube authentication failed: %s", exc)
                logger.error("Run 'python scripts/setup_youtube.py' to authenticate")
            except Exception as exc:
                logger.error("YouTube upload failed: %s", exc)
                logger.info("Video saved locally: %s", paths.final_video)
        else:
            logger.info("%s [7/7] Upload skipped (use --upload or --upload-private)", tag)

        if cleanup:
            for directory in (paths.audio_dir, paths.clips_dir, paths.scenes_dir):
                shutil.rmtree(directory, ignore_errors=True)
            logger.info("      File sementara (audio/clips/scenes) dihapus")
        return blueprint.title, paths.final_video

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _save_json(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _clip_dict(clip: Any) -> dict:
        url = getattr(clip, "pixabay_url", getattr(clip, "pexels_url", ""))
        return {
            "scene_number": clip.scene_number,
            "file": clip.path.name,
            "video_id": clip.video_id,
            "query": clip.query,
            "relevance_score": getattr(clip, "relevance_score", 0.0),
            "tags": getattr(clip, "tags", ""),
            "resolution": f"{clip.width}x{clip.height}",
            "duration": clip.duration,
            "url": url,
            "author": clip.author,
        }

    def _compose_description(self, base: str, music: Optional[MusicChoice]) -> str:
        description = base.strip()
        existing = {word.lower() for word in description.split() if word.startswith("#")}
        extra = [h if h.startswith("#") else f"#{h}" for h in self.channel.hashtags]
        if "#shorts" not in {h.lower() for h in extra}:
            extra.append("#shorts")
        extra = [h for h in extra if h.lower() not in existing]
        if extra:
            description += "\n\n" + " ".join(extra)
        if music and music.attribution:
            description += f"\n\n{music.attribution}"
        return description

    def _write_metadata(
        self,
        paths: RunPaths,
        package: ContentPackage,
        description: str,
        music: Optional[MusicChoice],
        duration: Optional[float],
    ) -> None:
        bp, report = package.blueprint, package.fact_check
        claims = "\n".join(
            f"- [{c.status}] {c.claim}\n    sumber: {c.source_hint}" + (f" | catatan: {c.note}" if c.note else "")
            for c in report.claims
        ) or "- (tidak ada)"
        audience = "Ya, dibuat untuk anak-anak" if self.channel.made_for_kids else "Tidak, video ini TIDAK dibuat untuk anak-anak"
        lines = [
            "JUDUL:",
            bp.title,
            "",
            "DESKRIPSI:",
            description,
            "",
            "TAGS:",
            ", ".join(bp.tags),
            "",
            "PENGATURAN YOUTUBE:",
            f"- Audiens: {audience} ({self.channel.target_audience})",
            "- Subtitle (opsional, upload sebagai CC): subtitles/subtitles.srt",
            "",
            "INFO PRODUKSI:",
            f"- Tanggal       : {datetime.now():%Y-%m-%d %H:%M}",
            f"- Sub-tema      : {bp.sub_theme}",
            f"- Topik         : {bp.topic}",
            f"- Gaya hook     : {package.hook_style}",
            f"- Durasi suara  : {duration:.1f} detik" if duration else "- Durasi suara  : (belum dirender)",
            f"- Musik         : {music.relative if music else '(tanpa musik)'}",
            "",
            "HASIL FACT-CHECK (untuk review internal - verifikasi sebelum upload):",
            f"- Verdict: {report.verdict} | confidence: {report.confidence:.2f}",
            f"- Alasan : {report.reason}",
            claims,
        ]
        paths.metadata_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _record_history(self, package: ContentPackage, output: Path, music: Optional[MusicChoice], status: str) -> None:
        bp = package.blueprint
        self.history.record(
            {
                "date": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "sub_theme": bp.sub_theme,
                "topic": bp.topic,
                "title": bp.title,
                "output": str(output),
                "music": music.relative if music else None,
            },
            music=music.relative if music else None,
        )

    def _upload_to_youtube(
        self, 
        paths: RunPaths, 
        blueprint: VideoBlueprint, 
        description: str, 
        privacy: str
    ) -> UploadResult:
        """Upload video to YouTube with metadata and thumbnail."""
        uploader = self._get_youtube_uploader()
        
        # Parse tags from blueprint
        tags = blueprint.tags[:15]  # YouTube max 500 chars total
        
        return uploader.upload_video(
            video_path=paths.final_video,
            title=blueprint.title,
            description=description,
            tags=tags,
            category_id=self.settings.youtube_category,
            privacy_status=privacy,
            made_for_kids=self.channel.made_for_kids,
            thumbnail_path=paths.thumbnail_file if paths.thumbnail_file.is_file() else None,
            captions_path=paths.srt_file if paths.srt_file.is_file() else None,
        )
