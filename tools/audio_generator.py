"""Edge-TTS voiceover generator: one clip per scene, auto-paced to hit the target duration."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import edge_tts

from config.settings import Settings
from schemas.blueprint import Scene
from tools.ffmpeg_utils import probe_duration, run_ffmpeg, write_concat_list

logger = logging.getLogger(__name__)

# Trim leading/trailing silence from each TTS clip, then add a short natural pause.
_TRIM_FILTER = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse,"
    "apad=pad_dur=0.12"
)


class AudioGenerationError(RuntimeError):
    """Raised when the voiceover cannot be synthesized."""


@dataclass
class SceneAudio:
    scene_number: int
    text: str
    path: Path
    duration: float
    start: float = 0.0


@dataclass
class VoiceoverResult:
    scenes: List[SceneAudio]
    voiceover_path: Path
    total_duration: float
    rate: int


def _clean_tts_text(text: str) -> str:
    text = re.sub(r"[*_#~`|<>\[\]{}]", " ", text)
    return " ".join(text.split())


class AudioGenerator:
    MAX_CONCURRENCY = 4
    RETRIES = 3

    def __init__(self, settings: Settings, voice: str | None = None) -> None:
        self.settings = settings
        self.voice = voice or settings.tts_voice

    async def _synthesize_scene(self, scene: Scene, audio_dir: Path, rate: int, semaphore: asyncio.Semaphore) -> SceneAudio:
        text = _clean_tts_text(scene.narration_text)
        if not text:
            raise AudioGenerationError(f"Scene {scene.scene_number} tidak memiliki narasi")
        mp3_path = audio_dir / f"scene_{scene.scene_number:02d}.mp3"
        wav_path = audio_dir / f"scene_{scene.scene_number:02d}.wav"
        rate_str = f"{rate:+d}%"

        async with semaphore:
            last_error: Exception | None = None
            for attempt in range(1, self.RETRIES + 1):
                try:
                    communicate = edge_tts.Communicate(text, self.voice, rate=rate_str)
                    await communicate.save(str(mp3_path))
                    if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
                        raise AudioGenerationError("Edge-TTS menghasilkan file kosong")
                    break
                except Exception as exc:  # noqa: BLE001 - edge-tts raises several network exception types
                    last_error = exc
                    logger.warning("      TTS scene %d gagal (percobaan %d/%d): %s", scene.scene_number, attempt, self.RETRIES, exc)
                    await asyncio.sleep(2 * attempt)
            else:
                raise AudioGenerationError(f"Edge-TTS gagal untuk scene {scene.scene_number}: {last_error}")

        await asyncio.to_thread(
            run_ffmpeg,
            ["-i", mp3_path, "-af", _TRIM_FILTER, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", wav_path],
            binary=self.settings.ffmpeg_binary,
        )
        duration = await asyncio.to_thread(probe_duration, wav_path, binary=self.settings.ffprobe_binary)
        return SceneAudio(scene_number=scene.scene_number, text=text, path=wav_path, duration=duration)

    async def _synthesize_all(self, scenes: Sequence[Scene], audio_dir: Path, rate: int) -> List[SceneAudio]:
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)
        results = await asyncio.gather(*(self._synthesize_scene(s, audio_dir, rate, semaphore) for s in scenes))
        return sorted(results, key=lambda item: item.scene_number)

    def _next_rate(self, rate: int, total: float) -> int:
        s = self.settings
        # Only adjust speed if video is too long (exceeds max duration)
        # Let natural speech determine the duration within the constraint
        if total > s.target_max_seconds:
            goal = s.target_max_seconds - 1.5
            factor = (1 + rate / 100.0) * total / goal
            new_rate = math.ceil((factor - 1) * 100)
            return max(s.tts_min_rate, min(s.tts_max_rate, new_rate))
        # If within constraint, keep natural speed
        return rate

    def generate(self, scenes: Sequence[Scene], audio_dir: Path) -> VoiceoverResult:
        """Synthesize every scene, adjust speaking rate to fit the duration window, and build voiceover.wav."""
        audio_dir.mkdir(parents=True, exist_ok=True)
        rate = self.settings.tts_base_rate
        scene_audio: List[SceneAudio] = []
        total = 0.0

        for attempt in range(1, 4):
            scene_audio = asyncio.run(self._synthesize_all(scenes, audio_dir, rate))
            total = sum(item.duration for item in scene_audio)
            logger.info("      Voiceover %.1f detik (rate %+d%%, percobaan %d)", total, rate, attempt)
            new_rate = self._next_rate(rate, total)
            if new_rate == rate:
                break
            logger.info("      Durasi terlalu panjang (%.1f detik). Menyesuaikan kecepatan bicara %+d%% -> %+d%%",
                        total, rate, new_rate)
            rate = new_rate

        if total > self.settings.target_max_seconds + 2:
            logger.warning("      Durasi voiceover %.1f detik melebihi maksimal %.0f detik; naskah terlalu panjang.", 
                          total, self.settings.target_max_seconds)

        cursor = 0.0
        for item in scene_audio:
            item.start = cursor
            cursor += item.duration

        list_file = audio_dir / "voiceover_list.txt"
        voiceover_path = audio_dir / "voiceover.wav"
        write_concat_list([item.path for item in scene_audio], list_file)
        run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", list_file.name, "-c", "copy", voiceover_path.name],
            binary=self.settings.ffmpeg_binary,
            cwd=audio_dir,
        )
        return VoiceoverResult(scenes=scene_audio, voiceover_path=voiceover_path, total_duration=total, rate=rate)
