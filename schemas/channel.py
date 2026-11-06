"""Channel profile loaded from data/channel.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SubTheme(BaseModel):
    name: str
    description: str = ""
    fallback_keywords: List[str] = Field(default_factory=list)


class ChannelProfile(BaseModel):
    channel_id: str
    channel_name: str
    niche: str
    language: str = "id"
    target_audience: str
    made_for_kids: bool = False
    voice: Optional[str] = None
    base_tags: List[str] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)
    content_rules: List[str] = Field(default_factory=list)
    generic_fallback_keywords: List[str] = Field(default_factory=list)
    sub_themes: List[SubTheme]

    @field_validator("sub_themes")
    @classmethod
    def _require_sub_themes(cls, value: List[SubTheme]) -> List[SubTheme]:
        if not value:
            raise ValueError("channel.json harus memiliki minimal 1 sub_theme")
        return value

    def find_sub_theme(self, name: str) -> SubTheme:
        wanted = name.strip().lower()
        for sub_theme in self.sub_themes:
            if sub_theme.name.lower() == wanted:
                return sub_theme
        for sub_theme in self.sub_themes:
            if wanted in sub_theme.name.lower():
                return sub_theme
        available = ", ".join(st.name for st in self.sub_themes)
        raise ValueError(f"Sub-tema '{name}' tidak ditemukan. Pilihan: {available}")


def load_channel(path: Path) -> ChannelProfile:
    with path.open("r", encoding="utf-8") as handle:
        return ChannelProfile.model_validate(json.load(handle))
