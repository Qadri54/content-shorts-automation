"""Batch CLI entrypoint for the YouTube Shorts factory.

Examples:
    python main.py                          # 1 video, sub-theme rotated automatically
    python main.py --count 3                # 3 videos in a row
    python main.py --sub-theme "Luar Angkasa"
    python main.py --blueprint-only         # only generate script + metadata (no rendering)
    python main.py --upload                 # produce + upload to YouTube (public)
    python main.py --upload-private         # produce + upload as private (for review)
    python main.py --check                  # verify FFmpeg, API keys, Gemini model and Pexels
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from config.settings import ConfigurationError, Settings, get_settings  # noqa: E402
from schemas.channel import load_channel  # noqa: E402


def configure_logging(log_file: Path, verbose: bool) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)
    for noisy in ("httpx", "httpcore", "urllib3", "LiteLLM", "litellm", "faster_whisper", "google_genai", "asyncio", "crewai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mesin konten YouTube Shorts otomatis (Fakta Unik)")
    parser.add_argument("--count", type=int, default=1, help="Jumlah video yang dibuat berurutan (default: 1)")
    parser.add_argument("--sub-theme", dest="sub_theme", default=None, help="Paksa sub-tema tertentu (nama di data/channel.json)")
    parser.add_argument("--blueprint-only", action="store_true", help="Hanya buat naskah, fact-check & metadata tanpa render")
    parser.add_argument("--cleanup", action="store_true", help="Hapus file sementara (audio/clips/scenes) setelah render sukses")
    parser.add_argument("--upload", action="store_true", help="Upload video ke YouTube (public)")
    parser.add_argument("--upload-private", action="store_true", help="Upload video ke YouTube sebagai private (untuk review)")
    parser.add_argument("--check", action="store_true", help="Cek kesiapan environment (FFmpeg, API key, model Gemini, Pexels)")
    parser.add_argument("--verbose", action="store_true", help="Tampilkan log detail termasuk proses agent CrewAI")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count minimal 1")
    return args


def run_check(settings: Settings) -> int:
    log = logging.getLogger("check")
    settings.validate_runtime()
    log.info("OK  ffmpeg  : %s", settings.ffmpeg_binary)
    log.info("OK  ffprobe : %s", settings.ffprobe_binary)
    channel = load_channel(settings.channel_file)
    log.info("OK  channel : %s (%d sub-tema)", channel.channel_name, len(channel.sub_themes))

    if settings.pixabay_api_key and not settings._is_missing(settings.pixabay_api_key):
        from tools.pixabay_downloader import PixabayDownloader

        if PixabayDownloader(settings.pixabay_api_key).ping():
            log.info("OK  Pixabay API")
        else:
            log.error("GAGAL Pixabay API tidak mengembalikan hasil")
            return 1
    elif settings.pexels_api_key and not settings._is_missing(settings.pexels_api_key):
        from tools.pexels_downloader import PexelsDownloader

        if PexelsDownloader(settings.pexels_api_key).ping():
            log.info("OK  Pexels API")
        else:
            log.error("GAGAL Pexels API tidak mengembalikan hasil")
            return 1
    else:
        log.error("GAGAL Belum ada PIXABAY_API_KEY di file .env")
        return 1

    from crews.content_crew import ContentCrew

    reply = ContentCrew(settings, channel).ping()
    log.info("OK  Gemini (%s) menjawab: %s", settings.gemini_model, reply.strip()[:60])

    music_files = [p for p in settings.music_dir.rglob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}]
    if music_files:
        log.info("OK  Musik latar: %d file", len(music_files))
    else:
        log.warning("--  Belum ada musik di data/music/<mood>/ (video tetap bisa dirender tanpa musik)")
    log.info("Semua pengecekan selesai. Siap menjalankan: python main.py")
    return 0


def main() -> int:
    args = parse_args()
    settings = get_settings()
    configure_logging(settings.log_file, args.verbose)
    log = logging.getLogger("main")

    try:
        if args.check:
            return run_check(settings)

        settings.validate_runtime(require_gemini=True, require_stock_video=not args.blueprint_only)
        channel = load_channel(settings.channel_file)

        from pipeline.runner import ShortsFactory

        log.info("Channel: %s | Niche: %s | Model: %s | Jumlah video: %d",
                 channel.channel_name, channel.niche, settings.gemini_model, args.count)
        factory = ShortsFactory(settings, channel, verbose=args.verbose)
        results = factory.run_batch(
            args.count, 
            args.sub_theme, 
            args.blueprint_only, 
            args.cleanup,
            args.upload,
            args.upload_private
        )
    except ConfigurationError as exc:
        log.error("%s", exc)
        return 2
    except ValueError as exc:
        log.error("Input tidak valid: %s", exc)
        return 2
    except KeyboardInterrupt:
        log.warning("Dihentikan oleh pengguna.")
        return 130
    except Exception as exc:  # noqa: BLE001
        log.exception("Kesalahan tak terduga: %s", exc)
        return 1

    log.info("=" * 70)
    log.info("RINGKASAN BATCH")
    for result in results:
        if result.success:
            log.info("  [OK]    #%d %s (%.0f dtk)\n            %s", result.index, result.title, result.elapsed, result.output)
        else:
            log.info("  [GAGAL] #%d %s", result.index, result.error)
    succeeded = sum(r.success for r in results)
    log.info("Berhasil %d dari %d video. Log lengkap: %s", succeeded, len(results), settings.log_file)
    return 0 if succeeded == len(results) else (1 if succeeded == 0 else 3)


if __name__ == "__main__":
    sys.exit(main())
