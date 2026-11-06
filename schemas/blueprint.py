"""Strict output contracts shared by the CrewAI layer and the media engine.

LLM-facing models intentionally have no default values so they map cleanly to
Gemini structured-output schemas.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

MUSIC_MOODS: tuple[str, ...] = ("mysterious", "curious", "upbeat", "dramatic", "calm")
MusicMood = Literal["mysterious", "curious", "upbeat", "dramatic", "calm"]


class ScriptDraft(BaseModel):
    """Raw script produced by the Scriptwriter agent."""

    topic: str = Field(description="Short name of the single fact covered, e.g. 'Gurita punya tiga jantung'")
    hook: str = Field(description="The opening sentence (max 12 words) designed to stop the scroll")
    script: str = Field(description="Full spoken narration in Indonesian, 140-160 words")
    key_claims: List[str] = Field(description="Every factual claim made in the script, one per item")


class ClaimCheck(BaseModel):
    """Verification result for a single factual claim."""

    claim: str = Field(description="The factual claim being checked")
    status: Literal["verified", "corrected", "removed"] = Field(description="Outcome of the check")
    note: str = Field(description="What was wrong or why it is correct")
    source_hint: str = Field(description="Reputable source or institution where this can be verified (no URLs)")


class FactCheckReport(BaseModel):
    """Output of the Fact-Checker agent."""

    verdict: Literal["APPROVED", "REVISED", "REJECTED"] = Field(description="Overall verdict")
    confidence: float = Field(description="Confidence from 0 to 1 that final_script is accurate")
    final_script: str = Field(description="Fact-checked narration in Indonesian, 130-170 words")
    claims: List[ClaimCheck] = Field(description="Per-claim verification results")
    reason: str = Field(description="One or two sentences explaining the verdict")


class Scene(BaseModel):
    """One visual beat of the short (roughly 3-5 seconds)."""

    scene_number: int = Field(description="1-based scene index")
    narration_text: str = Field(description="Exact narration words spoken during this scene")
    visual_intent: str = Field(default="", description="Literal physical visual description of what MUST appear on screen")
    b_roll_keywords: List[str] = Field(description="2-3 precise English search phrases (1-2 words each) directly depicting visual_intent")
    estimated_duration_seconds: float = Field(description="Estimated narration length in seconds")


class VideoBlueprint(BaseModel):
    """Complete production blueprint for one YouTube Short."""

    channel_id: str = Field(description="Channel identifier (fixed value provided in the task)")
    niche: str = Field(description="Channel niche (fixed value provided in the task)")
    sub_theme: str = Field(description="Sub-theme of this video (fixed value provided in the task)")
    topic: str = Field(description="Topic of this video (fixed value provided in the task)")
    title: str = Field(description="Indonesian YouTube title, max 70 characters")
    description: str = Field(description="Indonesian YouTube description, 2-3 sentences")
    tags: List[str] = Field(description="10-15 SEO tags")
    music_mood: MusicMood = Field(description="Background music mood")
    scenes: List[Scene] = Field(description="Ordered list of scenes")

    def full_script(self) -> str:
        return " ".join(scene.narration_text.strip() for scene in self.scenes if scene.narration_text.strip())
