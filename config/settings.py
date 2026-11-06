"""Application settings, directory layout and runtime validation."""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

_PLACEHOLDER_PREFIXES = ("your_", "isi_", "changeme")


class ConfigurationError(RuntimeError):
    """Raised when the runtime environment is not ready to run the pipeline."""


def slugify(text: str, max_length: int = 50) -> str:
    """Convert a title into a filesystem-safe ASCII slug."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "video"


@dataclass(frozen=True)
class RunPaths:
    """All filesystem locations used by a single video production run."""

    root: Path
    audio_dir: Path
    clips_dir: Path
    scenes_dir: Path
    subtitles_dir: Path
    blueprint_file: Path
    factcheck_file: Path
    metadata_file: Path
    final_video: Path
    thumbnail_file: Path
    upload_result_file: Path

    @property
    def ass_file(self) -> Path:
        return self.subtitles_dir / "subtitles.ass"

    @property
    def srt_file(self) -> Path:
        return self.subtitles_dir / "subtitles.srt"

    def create(self) -> "RunPaths":
        for directory in (self.root, self.audio_dir, self.clips_dir, self.scenes_dir, self.subtitles_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


class Settings(BaseSettings):
    """Environment-driven configuration (values are read from `.env`)."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- API keys ---
    gemini_api_key: str = ""
    pixabay_api_key: str = ""
    pexels_api_key: str = ""

    # --- YouTube Upload ---
    youtube_default_privacy: str = "public"
    youtube_category: str = "27"

    # --- LLM / CrewAI ---
    gemini_model: str = "gemini/gemini-2.5-flash"
    llm_temperature: float = 0.7
    agent_max_iter: int = 2
    crew_max_rpm: int = 10

    # --- Voiceover ---
    tts_voice: str = "id-ID-ArdiNeural"
    tts_base_rate: int = 8
    tts_max_rate: int = 30
    tts_min_rate: int = -10
    target_min_seconds: float = 50.0
    target_max_seconds: float = 59.0

    # --- Subtitles ---
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    subtitle_font: str = "Arial Black"
    subtitle_font_size: int = 88
    subtitle_margin_v: int = 520
    subtitle_max_words: int = 3

    # --- Video ---
    video_width: int = 1080
    video_height: int = 1920
    video_fps: int = 30
    video_crf: int = 20
    video_preset: str = "medium"
    end_tail_seconds: float = 0.6
    music_volume_db: float = -18.0

    # --- Batch ---
    delay_between_runs: float = 5.0

    # --- Binaries ---
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    # --- Paths ---
    data_dir: Path = DATA_DIR

    @model_validator(mode="after")
    def _check_ranges(self) -> "Settings":
        if self.target_min_seconds >= self.target_max_seconds:
            raise ValueError("TARGET_MIN_SECONDS harus lebih kecil dari TARGET_MAX_SECONDS")
        if not (self.tts_min_rate <= self.tts_base_rate <= self.tts_max_rate):
            raise ValueError("TTS_BASE_RATE harus berada di antara TTS_MIN_RATE dan TTS_MAX_RATE")
        if self.subtitle_max_words < 1:
            raise ValueError("SUBTITLE_MAX_WORDS minimal 1")
        return self

    # ------------------------------------------------------------------ paths
    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def music_dir(self) -> Path:
        return self.data_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.data_dir / "fonts"

    @property
    def channel_file(self) -> Path:
        return self.data_dir / "channel.json"

    @property
    def history_file(self) -> Path:
        return self.data_dir / "history.json"

    @property
    def log_file(self) -> Path:
        return self.output_dir / "factory.log"

    @property
    def config_dir(self) -> Path:
        return self.data_dir.parent / "config"

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.output_dir, self.music_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def create_run_paths(self, slug: str) -> RunPaths:
        root = self.output_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{slug}"
        return RunPaths(
            root=root,
            audio_dir=root / "audio",
            clips_dir=root / "clips",
            scenes_dir=root / "scenes",
            subtitles_dir=root / "subtitles",
            blueprint_file=root / "blueprint.json",
            factcheck_file=root / "factcheck.json",
            metadata_file=root / "metadata.txt",
            final_video=root / f"{slug}.mp4",
            thumbnail_file=root / "thumbnail.png",
            upload_result_file=root / "youtube_upload.json",
        )

    # ------------------------------------------------------------- validation
    @staticmethod
    def _is_missing(value: str) -> bool:
        cleaned = value.strip().lower()
        return not cleaned or cleaned.startswith(_PLACEHOLDER_PREFIXES)

    @staticmethod
    def _find_binary(name: str) -> str | None:
        candidate = Path(name)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(name)
        if found:
            return found
        if sys.platform.startswith("win"):
            exe = name if name.lower().endswith(".exe") else f"{name}.exe"
            extra_dirs = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
                Path("C:/ffmpeg/bin"),
                Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "ffmpeg" / "bin",
            ]
            for directory in extra_dirs:
                path = directory / exe
                if path.is_file():
                    return str(path)
        return None

    def validate_runtime(self, require_gemini: bool = True, require_stock_video: bool = True) -> None:
        """Validate API keys and FFmpeg availability; raise ConfigurationError listing every problem."""
        errors: list[str] = []

        if require_gemini and self._is_missing(self.gemini_api_key):
            errors.append("GEMINI_API_KEY belum diisi di file .env (https://aistudio.google.com/apikey)")
        if require_stock_video and self._is_missing(self.pixabay_api_key) and self._is_missing(self.pexels_api_key):
            errors.append("PIXABAY_API_KEY belum diisi di file .env (Daftar & ambil key instan di: https://pixabay.com/api/docs/)")

        ffmpeg_path = self._find_binary(self.ffmpeg_binary)
        ffprobe_path = self._find_binary(self.ffprobe_binary)
        if ffmpeg_path is None:
            errors.append("ffmpeg tidak ditemukan di PATH. Instal dengan: winget install Gyan.FFmpeg")
        else:
            self.ffmpeg_binary = ffmpeg_path
        if ffprobe_path is None:
            errors.append("ffprobe tidak ditemukan di PATH (biasanya terpasang bersama ffmpeg)")
        else:
            self.ffprobe_binary = ffprobe_path

        if not self.channel_file.is_file():
            errors.append(f"File profil channel tidak ditemukan: {self.channel_file}")

        if errors:
            raise ConfigurationError("Konfigurasi belum siap:\n  - " + "\n  - ".join(errors))

        self.ensure_directories()
        if self.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key
            os.environ["GOOGLE_API_KEY"] = self.gemini_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
