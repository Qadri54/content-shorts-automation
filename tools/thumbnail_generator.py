"""Thumbnail generator: template-based with hook text + video snapshot."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config.settings import Settings
from schemas.blueprint import VideoBlueprint

logger = logging.getLogger(__name__)


class ThumbnailGenerationError(RuntimeError):
    """Raised when thumbnail generation fails."""


@dataclass
class ThumbnailStyle:
    name: str
    bg_color_top: tuple[int, int, int]
    bg_color_bottom: tuple[int, int, int]
    text_color: tuple[int, int, int]
    text_stroke_color: tuple[int, int, int]
    text_stroke_width: int


MOOD_STYLES = {
    "mysterious": ThumbnailStyle(
        name="mysterious",
        bg_color_top=(25, 25, 60),
        bg_color_bottom=(60, 20, 80),
        text_color=(255, 220, 100),
        text_stroke_color=(0, 0, 0),
        text_stroke_width=4,
    ),
    "curious": ThumbnailStyle(
        name="curious",
        bg_color_top=(20, 100, 180),
        bg_color_bottom=(100, 180, 255),
        text_color=(255, 255, 255),
        text_stroke_color=(0, 50, 100),
        text_stroke_width=5,
    ),
    "upbeat": ThumbnailStyle(
        name="upbeat",
        bg_color_top=(255, 140, 0),
        bg_color_bottom=(255, 200, 50),
        text_color=(255, 255, 255),
        text_stroke_color=(150, 50, 0),
        text_stroke_width=5,
    ),
    "dramatic": ThumbnailStyle(
        name="dramatic",
        bg_color_top=(140, 0, 0),
        bg_color_bottom=(220, 50, 0),
        text_color=(255, 255, 255),
        text_stroke_color=(80, 0, 0),
        text_stroke_width=6,
    ),
    "calm": ThumbnailStyle(
        name="calm",
        bg_color_top=(40, 120, 100),
        bg_color_bottom=(100, 180, 160),
        text_color=(255, 255, 255),
        text_stroke_color=(20, 60, 50),
        text_stroke_width=4,
    ),
}

DEFAULT_STYLE = ThumbnailStyle(
    name="default",
    bg_color_top=(20, 80, 150),
    bg_color_bottom=(100, 150, 220),
    text_color=(255, 255, 255),
    text_stroke_color=(0, 40, 80),
    text_stroke_width=5,
)


class ThumbnailGenerator:
    WIDTH = 1280
    HEIGHT = 720
    SNAPSHOT_SIZE = 400
    BRANDING_TEXT = "FAKTA UNIK"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        blueprint: VideoBlueprint,
        video_path: Path,
        output_path: Path,
    ) -> Path:
        """Generate thumbnail from blueprint and video."""
        logger.info("      Generating thumbnail...")

        try:
            # Get style based on mood
            style = MOOD_STYLES.get(blueprint.music_mood, DEFAULT_STYLE)

            # Extract hook text (first sentence, max 60 chars)
            hook = self._extract_hook(blueprint)

            # Extract snapshot from video middle
            snapshot = self._extract_snapshot(video_path)

            # Create thumbnail
            thumbnail = self._create_thumbnail(hook, snapshot, style)

            # Save
            output_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.save(str(output_path), "PNG", quality=95)
            logger.info("      Thumbnail saved: %s (%.1f KB)", output_path.name, output_path.stat().st_size / 1024)

            return output_path

        except Exception as exc:
            logger.error("Thumbnail generation failed: %s", exc)
            # Fallback: simple snapshot with text
            return self._generate_fallback(blueprint, video_path, output_path)

    def _extract_hook(self, blueprint: VideoBlueprint) -> str:
        """Extract hook text from first scene."""
        if not blueprint.scenes:
            return blueprint.title[:60]

        first_scene = blueprint.scenes[0].narration_text.strip()
        # Take first sentence or first 60 chars
        sentences = first_scene.split(".")
        hook = sentences[0].strip()
        if len(hook) > 60:
            hook = hook[:57] + "..."
        return hook.upper()

    def _extract_snapshot(self, video_path: Path) -> Optional[Image.Image]:
        """Extract a frame from the middle of the video."""
        temp_frame = None
        try:
            # Get video duration
            probe_cmd = [
                self.settings.ffprobe_binary,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ]
            duration_str = subprocess.check_output(probe_cmd, text=True, timeout=10).strip()
            duration = float(duration_str)

            # Extract frame from middle with unique filename to avoid collisions
            timestamp = duration / 2
            import time
            temp_frame = video_path.parent / f"temp_snapshot_{int(time.time() * 1000)}.jpg"

            extract_cmd = [
                self.settings.ffmpeg_binary,
                "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"scale={self.SNAPSHOT_SIZE}:-1",
                "-y",
                str(temp_frame),
            ]
            subprocess.run(extract_cmd, check=True, capture_output=True, timeout=30)

            if temp_frame.is_file() and temp_frame.stat().st_size > 0:
                snapshot = Image.open(temp_frame)
                # Load into memory immediately
                snapshot.load()
                # Clean up temp file
                try:
                    temp_frame.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
                return snapshot

        except subprocess.TimeoutExpired:
            logger.warning("Snapshot extraction timed out")
        except Exception as exc:
            logger.warning("Failed to extract snapshot: %s", exc)
        finally:
            # Ensure cleanup even on error
            if temp_frame and temp_frame.exists():
                try:
                    temp_frame.unlink()
                except Exception:
                    pass

        return None

    def _create_thumbnail(
        self,
        hook: str,
        snapshot: Optional[Image.Image],
        style: ThumbnailStyle,
    ) -> Image.Image:
        """Create thumbnail with gradient background, text, and optional snapshot."""
        # Create canvas
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT))
        draw = ImageDraw.Draw(img)

        # Draw gradient background
        self._draw_gradient(img, style.bg_color_top, style.bg_color_bottom)

        # Add blurred snapshot if available
        if snapshot:
            self._add_snapshot_overlay(img, snapshot)

        # Add hook text (centered, multi-line)
        self._add_text(img, hook, style)

        # Add branding corner
        self._add_branding(img)

        return img

    def _draw_gradient(
        self,
        img: Image.Image,
        color_top: tuple[int, int, int],
        color_bottom: tuple[int, int, int],
    ) -> None:
        """Draw vertical gradient background."""
        draw = ImageDraw.Draw(img)
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
            g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
            b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b))

    def _add_snapshot_overlay(self, img: Image.Image, snapshot: Image.Image) -> None:
        """Add blurred snapshot to bottom right corner."""
        try:
            # Resize snapshot
            snapshot.thumbnail((self.SNAPSHOT_SIZE, self.SNAPSHOT_SIZE), Image.Resampling.LANCZOS)

            # Apply blur
            from PIL import ImageFilter
            snapshot = snapshot.filter(ImageFilter.GaussianBlur(radius=8))

            # Calculate position (bottom right with margin)
            x = self.WIDTH - snapshot.width - 40
            y = self.HEIGHT - snapshot.height - 40

            # Paste with transparency
            img.paste(snapshot, (x, y))

        except Exception as exc:
            logger.warning("Failed to add snapshot overlay: %s", exc)

    def _add_text(self, img: Image.Image, text: str, style: ThumbnailStyle) -> None:
        """Add centered text with stroke outline."""
        draw = ImageDraw.Draw(img)

        # Try to load custom font
        try:
            font = ImageFont.truetype("arialbd.ttf", 90)  # Arial Bold
        except Exception:
            try:
                font = ImageFont.truetype("Arial", 90)
            except Exception:
                font = ImageFont.load_default()

        # Word wrap text
        lines = self._wrap_text(text, font, draw, self.WIDTH - 120)

        # Calculate total height
        line_height = 110
        total_height = len(lines) * line_height
        y_start = (self.HEIGHT - total_height) // 2

        # Draw each line
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.WIDTH - text_width) // 2
            y = y_start + i * line_height

            # Draw stroke (outline)
            for dx in range(-style.text_stroke_width, style.text_stroke_width + 1):
                for dy in range(-style.text_stroke_width, style.text_stroke_width + 1):
                    if dx * dx + dy * dy <= style.text_stroke_width * style.text_stroke_width:
                        draw.text((x + dx, y + dy), line, font=font, fill=style.text_stroke_color)

            # Draw main text
            draw.text((x, y), line, font=font, fill=style.text_color)

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    def _add_branding(self, img: Image.Image) -> None:
        """Add small branding text to corner."""
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arialbd.ttf", 36)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                return

        # Bottom left corner
        x, y = 30, self.HEIGHT - 60
        
        # Draw with stroke
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                draw.text((x + dx, y + dy), self.BRANDING_TEXT, font=font, fill=(0, 0, 0))

        draw.text((x, y), self.BRANDING_TEXT, font=font, fill=(255, 200, 0))

    def _generate_fallback(self, blueprint: VideoBlueprint, video_path: Path, output_path: Path) -> Path:
        """Simple fallback: extract middle frame and overlay text."""
        logger.warning("Using fallback thumbnail generation...")

        try:
            timestamp = 25  # Middle of ~50 second video
            
            # Use unique temp file
            import time
            temp_output = output_path.parent / f"temp_thumb_{int(time.time() * 1000)}.png"
            
            extract_cmd = [
                self.settings.ffmpeg_binary,
                "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"scale={self.WIDTH}:{self.HEIGHT}:force_original_aspect_ratio=increase,crop={self.WIDTH}:{self.HEIGHT}",
                "-y",
                str(temp_output),
            ]
            subprocess.run(extract_cmd, check=True, capture_output=True, timeout=30)

            if temp_output.is_file() and temp_output.stat().st_size > 0:
                # Move to final location
                import shutil
                shutil.move(str(temp_output), str(output_path))
                logger.info("      Fallback thumbnail created: %s", output_path.name)
                return output_path

        except Exception as exc:
            logger.error("Fallback thumbnail also failed: %s", exc)

        raise ThumbnailGenerationError("Both thumbnail generation methods failed")
