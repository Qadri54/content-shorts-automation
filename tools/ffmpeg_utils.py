"""Thin, error-safe wrappers around the ffmpeg / ffprobe CLIs."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe invocation fails; carries the captured STDERR."""

    def __init__(self, message: str, command: Sequence[str] | None = None, stderr: str = "") -> None:
        self.command = list(command or [])
        self.stderr = stderr
        detail = f"\n--- STDERR (akhir) ---\n{stderr}" if stderr else ""
        super().__init__(f"{message}{detail}")


def _tail(text: str | bytes | None, lines: int = 25) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return "\n".join(text.strip().splitlines()[-lines:])


def run_ffmpeg(
    args: Sequence[str],
    *,
    binary: str = "ffmpeg",
    cwd: Path | None = None,
    timeout: float | None = 900,
) -> None:
    """Run ffmpeg with `args`; raise FFmpegError with STDERR on any failure."""
    command = [binary, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *map(str, args)]
    logger.debug("ffmpeg: %s", " ".join(command))
    try:
        process = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"Binary ffmpeg tidak ditemukan: {binary}", command) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timeout setelah {timeout} detik", command, _tail(exc.stderr)) from exc
    if process.returncode != 0:
        raise FFmpegError(f"ffmpeg gagal (exit code {process.returncode})", command, _tail(process.stderr))


def probe_duration(path: Path, *, binary: str = "ffprobe") -> float:
    """Return media duration in seconds using ffprobe."""
    command = [
        binary, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        process = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"Binary ffprobe tidak ditemukan: {binary}", command) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("ffprobe timeout", command, _tail(exc.stderr)) from exc
    if process.returncode != 0:
        raise FFmpegError(f"ffprobe gagal membaca {path.name}", command, _tail(process.stderr))
    try:
        return float(process.stdout.strip())
    except ValueError as exc:
        raise FFmpegError(f"ffprobe tidak mengembalikan durasi untuk {path.name}", command, process.stdout) from exc


def write_concat_list(entries: Sequence[Path], list_file: Path) -> None:
    """Write an ffmpeg concat-demuxer list using paths relative to the list file."""
    lines = []
    for entry in entries:
        relative = Path(entry).resolve().relative_to(list_file.parent.resolve()).as_posix()
        safe = relative.replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
