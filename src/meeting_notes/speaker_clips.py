"""Create short local audio examples for diarized speakers."""
from pathlib import Path
import re
import shutil
import subprocess

from .whisper import TranscriptSegment


def _clip_window(start: float, end: float, max_duration: float = 12.0) -> tuple[float, float]:
    start = max(0.0, float(start))
    end = max(start + 0.1, float(end))
    if end - start <= max_duration:
        return start, end
    return start, start + max_duration


def _safe_speaker_id(speaker: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(speaker)).strip("._")
    if not value:
        raise ValueError("Diarization returned an empty speaker label")
    return value


def _sample_segment(segments: list[TranscriptSegment], speaker: str, start: float, end: float):
    candidates = [segment for segment in segments if segment.speaker == speaker and min(segment.end, end) > max(segment.start, start)]
    if not candidates:
        candidates = [segment for segment in segments if segment.speaker == speaker]
    return max(candidates, key=lambda segment: (segment.end - segment.start, len(segment.text)), default=None)


def create_speaker_clips(audio_path: str | Path, output_dir: str | Path, segments: list[TranscriptSegment], turns) -> list[dict[str, str | float | None]]:
    """Extract one recognizable WAV clip and transcript sample per speaker."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to create speaker clips")
    by_speaker: dict[str, list[tuple[float, float]]] = {}
    for turn in turns or []:
        by_speaker.setdefault(str(turn.speaker), []).append((float(turn.start), float(turn.end)))
    for segment in segments:
        by_speaker.setdefault(segment.speaker, []).append((float(segment.start), float(segment.end)))
    clips_dir = Path(output_dir) / "speakers"
    clips_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for speaker in sorted(by_speaker):
        start, end = _clip_window(*max(by_speaker[speaker], key=lambda item: item[1] - item[0]))
        filename = f"{_safe_speaker_id(speaker)}.wav"
        target = clips_dir / filename
        command = [ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(audio_path), "-t", f"{end - start:.3f}", "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(target)]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode:
            raise RuntimeError(f"ffmpeg failed to create speaker clip: {completed.stderr[-1000:]}")
        sample = _sample_segment(segments, speaker, start, end)
        result.append({"id": speaker, "sample_text": sample.text if sample else "", "clip": f"speakers/{filename}", "start": start, "end": end})
    return result
