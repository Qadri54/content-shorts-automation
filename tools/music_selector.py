"""Mood-based background music picker with rotation and attribution lookup."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


@dataclass
class MusicChoice:
    path: Path
    relative: str
    mood: str
    attribution: str


class MusicSelector:
    def __init__(self, music_dir: Path) -> None:
        self.music_dir = music_dir
        self.credits = self._load_credits()

    def _load_credits(self) -> Dict[str, str]:
        credits_file = self.music_dir / "credits.json"
        if not credits_file.is_file():
            return {}
        try:
            raw = json.loads(credits_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("credits.json tidak bisa dibaca: %s", exc)
            return {}
        credits: Dict[str, str] = {}
        for key, value in raw.items():
            if key.startswith("_"):
                continue
            text = value.get("attribution", "") if isinstance(value, dict) else str(value)
            credits[key.replace("\\", "/").lower()] = text.strip()
        return credits

    def _tracks(self, folder: Path) -> List[Path]:
        if not folder.is_dir():
            return []
        return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)

    def select(self, mood: str, recent: Sequence[str] = ()) -> Optional[MusicChoice]:
        tracks = self._tracks(self.music_dir / mood)
        chosen_mood = mood
        if not tracks:
            tracks = self._tracks(self.music_dir)
            chosen_mood = "any"
        if not tracks:
            return None
        recent_set = {r.lower() for r in recent}
        relative_of = {t: t.relative_to(self.music_dir).as_posix() for t in tracks}
        fresh = [t for t in tracks if relative_of[t].lower() not in recent_set]
        track = random.choice(fresh or tracks)
        relative = relative_of[track]
        return MusicChoice(
            path=track,
            relative=relative,
            mood=chosen_mood,
            attribution=self.credits.get(relative.lower(), ""),
        )
