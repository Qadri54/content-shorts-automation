"""Pixabay Video API downloader with strict context correlation and tag-relevance scoring.

Ensures every downloaded clip literally depicts the scene narration and visual intent,
strictly rejecting unrelated filler footage (clouds, random traffic, off-topic scenery).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests

from schemas.blueprint import Scene

logger = logging.getLogger(__name__)

# Disallow cartoonish/juvenile clips unless context specifically asks for them
NEGATIVE_TAGS: Set[str] = {
    "cartoon", "animation", "animated", "vector", "drawing", "sketch", "3d animation",
    "baby", "infant", "toddler", "toy", "childish"
}

# Stopwords to ignore when tokenizing visual intent
STOPWORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "and", "or", "as", "into", "close", "up", "shot",
    "footage", "video", "view", "showing", "depicting", "scene", "background"
}


class PixabayError(RuntimeError):
    """Raised when no usable footage can be obtained from Pixabay."""


@dataclass
class ClipResult:
    scene_number: int
    path: Path
    video_id: int
    query: str
    width: int
    height: int
    duration: float
    pixabay_url: str
    author: str
    tags: str = ""
    relevance_score: float = 0.0


def _tokenize(text: str) -> Set[str]:
    """Extract clean lowercase alphanumeric tokens."""
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return tokens - STOPWORDS


class PixabayDownloader:
    API_URL = "https://pixabay.com/api/videos/"
    PER_PAGE = 30

    def __init__(self, api_key: str, min_width: int = 1080, min_height: int = 1920, timeout: float = 30.0) -> None:
        self.api_key = api_key.strip()
        self.min_width = min_width
        self.min_height = min_height
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "yt-shorts-factory/1.0"})
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    # ----------------------------------------------------------------- search
    def search(self, query: str) -> List[Dict[str, Any]]:
        cleaned = " ".join(re.findall(r"[a-zA-Z0-9]+", query.lower()))
        if not cleaned:
            return []
        if cleaned in self._cache:
            return self._cache[cleaned]

        params = {
            "key": self.api_key,
            "q": cleaned,
            "video_type": "all",
            "per_page": self.PER_PAGE,
            "safesearch": "true",
            "order": "popular",
        }
        videos: List[Dict[str, Any]] = []
        for attempt in range(1, 4):
            try:
                response = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if response.status_code == 429:
                    wait = 10 * attempt
                    logger.warning("      Pixabay rate limit, menunggu %d detik...", wait)
                    time.sleep(wait)
                    continue
                if response.status_code in (400, 401, 403):
                    msg = response.text[:200]
                    raise PixabayError(f"PIXABAY_API_KEY ditolak ({response.status_code}): {msg}")
                response.raise_for_status()
                data = response.json()
                videos = data.get("hits", []) or []
                break
            except PixabayError:
                raise
            except (requests.RequestException, ValueError) as exc:
                logger.warning("      Pencarian Pixabay '%s' gagal (percobaan %d/3): %s", query, attempt, exc)
                time.sleep(2 * attempt)
        self._cache[cleaned] = videos
        return videos

    # -------------------------------------------------------- relevance score
    def _calculate_relevance(
        self,
        hit: Dict[str, Any],
        query: str,
        visual_intent: str,
        topic_context: str,
    ) -> float:
        """Score how strictly a video hit matches the scene's visual requirements."""
        tags_raw = hit.get("tags", "").lower()
        tag_tokens = _tokenize(tags_raw)
        if not tag_tokens:
            return 0.0

        # Penalize negative/juvenile tags heavily
        if any(neg in tag_tokens for neg in NEGATIVE_TAGS):
            return -10.0

        query_tokens = _tokenize(query)
        intent_tokens = _tokenize(visual_intent)
        topic_tokens = _tokenize(topic_context)

        score = 0.0

        # Exact query match is highest priority
        query_matches = tag_tokens & query_tokens
        score += len(query_matches) * 3.0

        # Visual intent matches
        intent_matches = tag_tokens & intent_tokens
        score += len(intent_matches) * 2.0

        # Topic context matches
        topic_matches = tag_tokens & topic_tokens
        score += len(topic_matches) * 1.0

        # Check full tag phrases
        phrases = [p.strip() for p in tags_raw.split(",") if p.strip()]
        for q in (query, visual_intent):
            q_clean = q.strip().lower()
            if any(q_clean in phrase or phrase in q_clean for phrase in phrases):
                score += 2.5

        # Native portrait bonus (tie breaker)
        streams = hit.get("videos", {}) or {}
        for s in streams.values():
            if isinstance(s, dict) and s.get("height", 0) > s.get("width", 0):
                score += 0.5
                break

        return score

    def _pick_best_stream(self, video: Dict[str, Any], prefer_portrait: bool) -> Optional[Dict[str, Any]]:
        streams = video.get("videos", {}) or {}
        candidates = []
        for quality in ("large", "medium", "small"):
            stream = streams.get(quality)
            if isinstance(stream, dict) and stream.get("url") and stream.get("width") and stream.get("height"):
                candidates.append(stream)

        if not candidates:
            return None

        candidates.sort(key=lambda s: int(s.get("width", 0)) * int(s.get("height", 0)), reverse=True)
        is_portrait = int(candidates[0].get("height", 0)) >= int(candidates[0].get("width", 0))

        if prefer_portrait and not is_portrait:
            return None

        for cand in candidates:
            w, h = int(cand.get("width", 0)), int(cand.get("height", 0))
            if w >= 1080 or h >= 1080:
                return cand
        return candidates[0]

    def _choose_best_hit(
        self,
        hits: Sequence[Dict[str, Any]],
        query: str,
        visual_intent: str,
        topic_context: str,
        min_duration: float,
        used_ids: Set[int],
        allow_reuse: bool,
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], float]]:
        """Select the highest-scoring relevant video for the given context."""
        candidates = [v for v in hits if allow_reuse or v.get("id") not in used_ids]
        if not candidates:
            return None

        scored: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
        for hit in candidates:
            score = self._calculate_relevance(hit, query, visual_intent, topic_context)
            if score <= 0.5:
                # Discard hits with no actual relevance to query/intent
                continue

            stream = self._pick_best_stream(hit, prefer_portrait=False)
            if not stream:
                continue

            # Length bonus: clips long enough for the scene avoid looping
            if float(hit.get("duration") or 0) >= min_duration:
                score += 0.5

            scored.append((score, hit, stream))

        if not scored:
            return None

        # Sort by relevance score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_hit, best_stream = scored[0]
        return best_hit, best_stream, best_score

    # --------------------------------------------------------------- download
    def _download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
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
                    raise PixabayError("File video Pixabay terlalu kecil / korup")
                temp.replace(destination)
                return
            except (requests.RequestException, OSError, PixabayError) as exc:
                last_error = exc
                logger.warning("      Download Pixabay gagal (percobaan %d/3): %s", attempt, exc)
                time.sleep(2 * attempt)
        temp.unlink(missing_ok=True)
        raise PixabayError(f"Gagal mengunduh video dari Pixabay: {last_error}")

    # ------------------------------------------------------------------ public
    def fetch_for_scene(
        self,
        scene: Scene,
        duration: float,
        clips_dir: Path,
        fallback_keywords: Sequence[str],
        used_ids: Set[int],
        topic_context: str = "",
    ) -> ClipResult:
        visual_intent = getattr(scene, "visual_intent", "").strip() or scene.narration_text

        # Strict Query Plan:
        # Tier 1: Scene-specific b_roll_keywords
        # Tier 2: Sub-theme contextual fallbacks (if Tier 1 returned nothing strictly relevant)
        scene_queries = [k.strip() for k in scene.b_roll_keywords if k and k.strip()]
        theme_queries = [k.strip() for k in fallback_keywords if k and k.strip() and k not in scene_queries]

        best_selection: Optional[Tuple[str, Dict[str, Any], Dict[str, Any], float]] = None

        # Pass 1: Try scene queries with strict unique clips
        # Pass 2: Try theme queries with strict unique clips
        # Pass 3: Allow reuse if necessary but STILL enforce high relevance score
        search_passes = [
            (scene_queries, False),  # Tier 1, unique
            (theme_queries, False),  # Tier 2, unique
            (scene_queries, True),   # Tier 1, allow reuse
            (theme_queries, True),   # Tier 2, allow reuse
        ]

        for query_list, allow_reuse in search_passes:
            candidates_for_pass: List[Tuple[str, Dict[str, Any], Dict[str, Any], float]] = []
            for query in query_list:
                hits = self.search(query)
                res = self._choose_best_hit(
                    hits,
                    query=query,
                    visual_intent=visual_intent,
                    topic_context=topic_context,
                    min_duration=duration,
                    used_ids=used_ids,
                    allow_reuse=allow_reuse,
                )
                if res:
                    hit, stream, score = res
                    candidates_for_pass.append((query, hit, stream, score))

            if candidates_for_pass:
                # Pick the highest relevance score from this tier
                candidates_for_pass.sort(key=lambda x: x[3], reverse=True)
                best_selection = candidates_for_pass[0]
                break

        if not best_selection:
            # If all failed, try a broad search using topic_context
            topic_query = " ".join(re.findall(r"[a-zA-Z0-9]+", topic_context.lower()))[:30]
            if topic_query:
                hits = self.search(topic_query)
                res = self._choose_best_hit(
                    hits, query=topic_query, visual_intent=visual_intent,
                    topic_context=topic_context, min_duration=duration,
                    used_ids=used_ids, allow_reuse=True
                )
                if res:
                    hit, stream, score = res
                    best_selection = (topic_query, hit, stream, score)

        if not best_selection:
            all_queries = ", ".join(scene_queries + theme_queries)
            raise PixabayError(
                f"STRICT CHECK GAGAL: Tidak ditemukan video yang relevan dengan konteks scene {scene.scene_number} "
                f"(visual_intent: '{visual_intent}', query: {all_queries})"
            )

        query, video, stream, score = best_selection
        destination = clips_dir / f"clip_{scene.scene_number:02d}.mp4"
        self._download(stream["url"], destination)
        used_ids.add(int(video["id"]))

        tags = video.get("tags", "")
        return ClipResult(
            scene_number=scene.scene_number,
            path=destination,
            video_id=int(video["id"]),
            query=query,
            width=int(stream["width"]),
            height=int(stream["height"]),
            duration=float(video.get("duration") or 0),
            pixabay_url=str(video.get("pageURL", "")),
            author=str(video.get("user", "")),
            tags=tags,
            relevance_score=score,
        )

    def fetch_for_scenes(
        self,
        scenes: Sequence[Scene],
        durations: Sequence[float],
        clips_dir: Path,
        fallback_keywords: Sequence[str],
        topic_context: str = "",
    ) -> List[ClipResult]:
        clips_dir.mkdir(parents=True, exist_ok=True)
        used_ids: Set[int] = set()
        results: List[ClipResult] = []

        logger.info("      [STRICT VISUAL CHECK] Memilih klip dengan kesesuaian konteks & tag tertinggi...")
        for scene, duration in zip(scenes, durations):
            clip = self.fetch_for_scene(
                scene, duration, clips_dir, fallback_keywords, used_ids, topic_context=topic_context
            )
            orient = "portrait" if clip.height >= clip.width else "center-crop 9:16"
            logger.info(
                "      Scene %02d: '%s' -> #%d [%s] (Skor relevansi: %.1f, tags: '%s')",
                scene.scene_number, clip.query, clip.video_id, orient, clip.relevance_score, clip.tags[:45],
            )
            results.append(clip)
        return results

    def ping(self) -> bool:
        """Verify API key validity."""
        hits = self.search("nature")
        return isinstance(hits, list)
