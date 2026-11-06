"""Persistent production history: topic de-duplication, sub-theme rotation and music rotation."""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from schemas.channel import ChannelProfile, SubTheme

logger = logging.getLogger(__name__)


class HistoryStore:
    RECENT_MUSIC_LIMIT = 5

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                backup = self.path.with_suffix(".corrupt.json")
                logger.warning("history.json rusak (%s); dicadangkan ke %s", exc, backup.name)
                self.path.replace(backup)
                data = {}
        data.setdefault("videos", [])
        data.setdefault("recent_music", [])
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    @property
    def videos(self) -> List[Dict[str, Any]]:
        return self.data["videos"]

    def pick_sub_theme(self, channel: ChannelProfile) -> SubTheme:
        """Weighted selection: prioritize high-retention sensory topics (60% sensory, 20% body, 20% others)"""
        
        # Define category weights based on proven performance
        SENSORY_THEMES = ["Sensasi Makanan", "Kuliner", "Makanan & Kuliner Dunia"]
        BODY_THEMES = ["Sains & Tubuh Manusia"]
        
        # Calculate weights
        weights = {}
        for st in channel.sub_themes:
            if st.name in SENSORY_THEMES:
                weights[st.name] = 6  # 60% total
            elif st.name in BODY_THEMES:
                weights[st.name] = 2  # 20% total
            else:
                weights[st.name] = 1  # 20% total (distributed)
        
        # Still respect least-used rotation to avoid repetition
        counts = Counter(video.get("sub_theme") for video in self.videos)
        last = self.videos[-1].get("sub_theme") if self.videos else None
        
        # Apply weights to least-used themes
        lowest_count = min(counts.get(st.name, 0) for st in channel.sub_themes)
        candidates = [
            st for st in channel.sub_themes 
            if counts.get(st.name, 0) == lowest_count and st.name != last
        ]
        
        if not candidates:
            candidates = [st for st in channel.sub_themes if st.name != last] or list(channel.sub_themes)
        
        # Weighted random choice
        total_weight = sum(weights.get(st.name, 1) for st in candidates)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for st in candidates:
            cumulative += weights.get(st.name, 1)
            if r <= cumulative:
                return st
        
        return candidates[-1]  # fallback

    def recent_topics(self, sub_theme: Optional[str] = None, overall_limit: int = 30, theme_limit: int = 60) -> List[str]:
        topics: List[str] = []
        if sub_theme:
            topics += [v["topic"] for v in self.videos if v.get("sub_theme") == sub_theme and v.get("topic")][-theme_limit:]
        topics += [v["topic"] for v in self.videos if v.get("topic")][-overall_limit:]
        seen, unique = set(), []
        for topic in topics:
            if topic.lower() not in seen:
                seen.add(topic.lower())
                unique.append(topic)
        return unique

    def recent_music(self) -> List[str]:
        return list(self.data["recent_music"])

    def record(self, entry: Dict[str, Any], music: Optional[str] = None) -> None:
        self.videos.append(entry)
        if music:
            recent = [m for m in self.data["recent_music"] if m != music] + [music]
            self.data["recent_music"] = recent[-self.RECENT_MUSIC_LIMIT :]
        self.save()
