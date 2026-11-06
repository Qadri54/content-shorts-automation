"""Word-level subtitles: faster-whisper timestamps aligned to the known narration text.

Whisper supplies *timing*; the approved script supplies *spelling*. Aligning the two
means subtitles never show transcription mistakes (names, numbers, Indonesian slang).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from config.settings import Settings
from tools.audio_generator import SceneAudio

logger = logging.getLogger(__name__)

YELLOW = "&H0000F5FF&"  # ASS colours are &HBBGGRR
CHUNK_BREAK_GAP = 0.45
MAX_CHUNK_CHARS = 20


@dataclass
class WordTiming:
    text: str
    start: float
    end: float


def _norm(token: str) -> str:
    return re.sub(r"[^\w]", "", token.lower())


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for raw in text.split():
        if _norm(raw):
            tokens.append(raw)
        elif tokens:
            tokens[-1] += raw  # attach stray punctuation (e.g. "—") to the previous word
    return tokens


def _distribute(tokens: Sequence[str], start: float, end: float) -> List[Tuple[float, float]]:
    if end - start < 0.06 * len(tokens):
        end = start + 0.06 * len(tokens)
    weights = [max(len(_norm(t)), 1) for t in tokens]
    total = float(sum(weights))
    spans, cursor = [], start
    for weight in weights:
        length = (end - start) * weight / total
        spans.append((cursor, cursor + length))
        cursor += length
    return spans


def align_words(text: str, whisper_words: Sequence[WordTiming], duration: float) -> List[WordTiming]:
    """Map whisper word timings onto the script tokens using sequence alignment."""
    tokens = _tokenize(text)
    if not tokens:
        return []
    if not whisper_words:
        return [WordTiming(t, s, e) for t, (s, e) in zip(tokens, _distribute(tokens, 0.0, duration))]

    timings: List[Optional[Tuple[float, float]]] = [None] * len(tokens)
    matcher = SequenceMatcher(None, [_norm(t) for t in tokens], [_norm(w.text) for w in whisper_words], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                word = whisper_words[j1 + k]
                timings[i1 + k] = (word.start, word.end)
        elif tag == "replace":
            span_start, span_end = whisper_words[j1].start, whisper_words[j2 - 1].end
            for k, span in enumerate(_distribute(tokens[i1:i2], span_start, span_end)):
                timings[i1 + k] = span

    # Fill script words whisper missed by interpolating between known neighbours.
    index = 0
    while index < len(tokens):
        if timings[index] is not None:
            index += 1
            continue
        run_end = index
        while run_end < len(tokens) and timings[run_end] is None:
            run_end += 1
        gap_start = timings[index - 1][1] if index > 0 else 0.0  # type: ignore[index]
        gap_end = timings[run_end][0] if run_end < len(tokens) else duration  # type: ignore[index]
        for k, span in enumerate(_distribute(tokens[index:run_end], gap_start, max(gap_end, gap_start))):
            timings[index + k] = span
        index = run_end

    result: List[WordTiming] = []
    previous_start = 0.0
    for token, span in zip(tokens, timings):
        start, end = span  # type: ignore[misc]
        start = min(max(start, previous_start), duration)
        end = min(max(end, start + 0.05), duration)
        result.append(WordTiming(token, start, end))
        previous_start = start
    return result


def _ass_time(seconds: float) -> str:
    centis = int(round(max(seconds, 0.0) * 100))
    hours, rem = divmod(centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _srt_time(seconds: float) -> str:
    millis = int(round(max(seconds, 0.0) * 1000))
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _display(token: str) -> str:
    cleaned = token.replace("{", "").replace("}", "").replace("\\", "")
    cleaned = re.sub(r"[\"“”‘’'«»]", "", cleaned)
    cleaned = cleaned.strip(".,;:—–-")
    return cleaned.upper()


class SubtitleGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info("      Memuat model faster-whisper '%s' (unduhan otomatis saat pertama kali)...", self.settings.whisper_model)
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        return self._model

    def transcribe(self, audio: SceneAudio) -> List[WordTiming]:
        model = self._load_model()
        segments, _info = model.transcribe(
            str(audio.path),
            language="id",
            word_timestamps=True,
            initial_prompt=audio.text,
            beam_size=5,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        words: List[WordTiming] = []
        for segment in segments:
            for word in segment.words or []:
                if word.word.strip():
                    words.append(WordTiming(word.word.strip(), float(word.start), float(word.end)))
        return words

    def build_word_timeline(self, scene_audio: Sequence[SceneAudio]) -> List[WordTiming]:
        timeline: List[WordTiming] = []
        for audio in scene_audio:
            try:
                raw_words = self.transcribe(audio)
            except Exception as exc:  # noqa: BLE001 - fall back to proportional timing rather than failing the video
                logger.warning("      Whisper gagal di scene %d (%s); memakai timing proporsional", audio.scene_number, exc)
                raw_words = []
            for word in align_words(audio.text, raw_words, audio.duration):
                timeline.append(WordTiming(word.text, word.start + audio.start, word.end + audio.start))
        return timeline

    @staticmethod
    def _chunk(words: Sequence[WordTiming], max_words: int) -> List[List[WordTiming]]:
        chunks: List[List[WordTiming]] = []
        current: List[WordTiming] = []
        for word in words:
            if current:
                previous = current[-1]
                chars = sum(len(w.text) + 1 for w in current) + len(word.text)
                if (
                    len(current) >= max_words
                    or chars > MAX_CHUNK_CHARS
                    or previous.text.rstrip("\"'”’)").endswith((".", ",", "!", "?", ";", ":"))
                    or word.start - previous.end > CHUNK_BREAK_GAP
                ):
                    chunks.append(current)
                    current = []
            current.append(word)
        if current:
            chunks.append(current)
        return chunks

    def _ass_header(self) -> str:
        s = self.settings
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {s.video_width}\n"
            f"PlayResY: {s.video_height}\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: Default,{s.subtitle_font},{s.subtitle_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,"
            f"-1,0,0,0,100,100,1,0,1,7,3,2,70,70,{s.subtitle_margin_v},1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

    def write_files(self, words: Sequence[WordTiming], ass_path: Path, srt_path: Path, total_duration: float) -> None:
        chunks = self._chunk(words, self.settings.subtitle_max_words)
        events: List[str] = []
        srt_lines: List[str] = []

        for c_index, chunk in enumerate(chunks):
            next_chunk_start = chunks[c_index + 1][0].start if c_index + 1 < len(chunks) else total_duration
            chunk_end = chunk[-1].end
            if next_chunk_start - chunk_end < 0.35:
                chunk_end = next_chunk_start
            display = [_display(w.text) for w in chunk]

            for w_index, word in enumerate(chunk):
                start = word.start
                end = chunk[w_index + 1].start if w_index + 1 < len(chunk) else chunk_end
                if end <= start:
                    continue
                parts = []
                for d_index, text in enumerate(display):
                    if d_index == w_index:
                        parts.append(
                            f"{{\\c{YELLOW}\\fscx112\\fscy112\\t(0,80,\\fscx106\\fscy106)}}{text}{{\\r}}"
                        )
                    else:
                        parts.append(text)
                pop = "{\\fscx92\\fscy92\\t(0,70,\\fscx100\\fscy100)}" if w_index == 0 else ""
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{pop}{' '.join(parts)}")

            plain = " ".join(re.sub(r"[{}\\]", "", w.text) for w in chunk)
            srt_lines.append(f"{c_index + 1}\n{_srt_time(chunk[0].start)} --> {_srt_time(chunk_end)}\n{plain}\n")

        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text(self._ass_header() + "\n".join(events) + "\n", encoding="utf-8")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

    def generate(self, scene_audio: Sequence[SceneAudio], ass_path: Path, srt_path: Path) -> List[WordTiming]:
        words = self.build_word_timeline(scene_audio)
        total = sum(audio.duration for audio in scene_audio)
        self.write_files(words, ass_path, srt_path, total)
        logger.info("      %d kata ter-timestamp -> %s", len(words), ass_path.name)
        return words
