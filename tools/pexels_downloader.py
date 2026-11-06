"""Pexels Video API downloader for vertical (9:16) B-roll."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from schemas.blueprint import Scene

logger = logging.getLogger(__name__)


class PexelsError(RuntimeError):
    """Raised when no usable footage can be obtained."""


@dataclass
class ClipResult:
    scene_number: int
    path: Path
    video_id: int
    query: str
    width: int
    height: int
    duration: float
    pexels_url: str
    author: str


class PexelsDownloader:
    API_URL = "https://api.pexels.com/videos/search"
    PER_PAGE = 20

    def __init__(self, api_key: str, min_width: int = 1080, min_height: int = 1920, timeout: float = 30.0) -> None:
        self.min_width = min_width
        self.min_height = min_height
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": api_key, "User-Agent": "yt-shorts-factory/1.0"})
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    # ----------------------------------------------------------------- search
    def search(self, query: str) -> List[Dict[str, Any]]:
        key = query.strip().lower()
        if key in self._cache:
            return self._cache[key]
        params = {"query": query, "orientation": "portrait", "per_page": self.PER_PAGE}
        videos: List[Dict[str, Any]] = []
        for attempt in range(1, 4):
            try:
                response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if response.status_code == 429:
                    wait = 10 * attempt
                    logger.warning("      Pexels rate limit, menunggu %d detik...", wait)
                    time.sleep(wait)
                    continue
                if response.status_code in (401, 403):
                    raise PexelsError("PEXELS_API_KEY ditolak (401/403). Periksa kembali key Anda.")
                response.raise_for_status()
                videos = response.json().get("videos", []) or []
                break
            except PexelsError:
                raise
            except (requests.RequestException, ValueError) as exc:
                logger.warning("      Pencarian Pexels '%s' gagal (percobaan %d/3): %s", query, attempt, exc)
                time.sleep(2 * attempt)
        self._cache[key] = videos
        return videos

    def _portrait_files(self, video: Dict[str, Any]) -> List[Dict[str, Any]]:
        files = []
        for item in video.get("video_files", []) or []:
            width, height = item.get("width") or 0, item.get("height") or 0
            if item.get("file_type") == "video/mp4" and item.get("link") and height > width > 0:
                files.append(item)
        return files

    def _pick_file(self, video: Dict[str, Any], require_full_hd: bool) -> Optional[Dict[str, Any]]:
        files = self._portrait_files(video)
        full_hd = [f for f in files if f["width"] >= self.min_width and f["height"] >= self.min_height]
        if full_hd:
            # Smallest file that still meets Full HD keeps downloads and encoding fast (avoids 4K).
            return min(full_hd, key=lambda f: f["width"] * f["height"])
        if require_full_hd:
            return None
        usable = [f for f in files if f["width"] >= 720]
        return max(usable, key=lambda f: f["width"] * f["height"]) if usable else None

    def _choose(
        self, videos: Sequence[Dict[str, Any]], min_duration: float, used_ids: set[int], require_full_hd: bool, allow_reuse: bool
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        candidates = [v for v in videos if allow_reuse or v.get("id") not in used_ids]
        # Prefer clips long enough for the scene, then accept shorter ones (they will be looped).
        for need_length in (True, False):
            for video in candidates:
                if need_length and float(video.get("duration") or 0) < min_duration:
                    continue
                chosen = self._pick_file(video, require_full_hd)
                if chosen:
                    return video, chosen
        return None

    # --------------------------------------------------------------- download
    def _download(self, url: str, destination: Path) -> None:
        temp = destination.with_suffix(".part")
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with self.session.get(url, stream=True, timeout=(self.timeout, 120)) as response:
                    response.raise_for_status()
                    with temp.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                if temp.stat().st_size < 10_000:
                    raise PexelsError("File video terlalu kecil / korup")
                temp.replace(destination)
                return
            except (requests.RequestException, OSError, PexelsError) as exc:
                last_error = exc
                logger.warning("      Download gagal (percobaan %d/3): %s", attempt, exc)
                time.sleep(2 * attempt)
        temp.unlink(missing_ok=True)
        raise PexelsError(f"Gagal mengunduh video dari Pexels: {last_error}")

    # ------------------------------------------------------------------ public
    def fetch_for_scene(
        self,
        scene: Scene,
        duration: float,
        clips_dir: Path,
        fallback_keywords: Sequence[str],
        used_ids: set[int],
    ) -> ClipResult:
        queries: List[str] = []
        for query in list(scene.b_roll_keywords) + list(fallback_keywords):
            q = " ".join(query.split())
            if q and q.lower() not in (x.lower() for x in queries):
                queries.append(q)

        selection = None
        # Pass 1: Full HD only. Pass 2: allow HD. Pass 3: allow reusing a clip already used in this video.
        for require_full_hd, allow_reuse in ((True, False), (False, False), (False, True)):
            for query in queries:
                picked = self._choose(self.search(query), duration, used_ids, require_full_hd, allow_reuse)
                if picked:
                    selection = (query, *picked)
                    break
            if selection:
                break
        if not selection:
            raise PexelsError(f"Tidak ada footage Pexels untuk scene {scene.scene_number} (query: {', '.join(queries)})")

        query, video, file_info = selection
        destination = clips_dir / f"clip_{scene.scene_number:02d}.mp4"
        self._download(file_info["link"], destination)
        used_ids.add(int(video["id"]))
        return ClipResult(
            scene_number=scene.scene_number,
            path=destination,
            video_id=int(video["id"]),
            query=query,
            width=int(file_info["width"]),
            height=int(file_info["height"]),
            duration=float(video.get("duration") or 0),
            pexels_url=str(video.get("url", "")),
            author=str((video.get("user") or {}).get("name", "")),
        )

    def fetch_for_scenes(
        self,
        scenes: Sequence[Scene],
        durations: Sequence[float],
        clips_dir: Path,
        fallback_keywords: Sequence[str],
    ) -> List[ClipResult]:
        clips_dir.mkdir(parents=True, exist_ok=True)
        used_ids: set[int] = set()
        results: List[ClipResult] = []
        for scene, duration in zip(scenes, durations):
            clip = self.fetch_for_scene(scene, duration, clips_dir, fallback_keywords, used_ids)
            hd_note = "" if clip.width >= self.min_width else " (di bawah Full HD, akan di-upscale)"
            logger.info("      Scene %02d: '%s' -> Pexels #%d %dx%d%s", scene.scene_number, clip.query, clip.video_id, clip.width, clip.height, hd_note)
            results.append(clip)
        return results

    def ping(self) -> bool:
        return bool(self.search("nature"))
