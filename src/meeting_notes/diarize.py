"""Cached pyannote diarization plus a deterministic local fallback."""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import math, os
import numpy as np
from .whisper import TranscriptSegment
@dataclass
class DiarizationTurn:
    start: float
    end: float
    speaker: str
def diarize(audio_path: str, config) -> list[DiarizationTurn]:
    method = config.method.lower()
    if method in {"auto", "pyannote"}:
        try: return _pyannote_diarize(audio_path, config)
        except Exception as exc:
            if method == "pyannote": raise RuntimeError(f"Pyannote unavailable: {exc}") from exc
    return _energy_cluster_diarize(audio_path, config.max_speakers)
def _pyannote_diarize(audio_path: str, config) -> list[DiarizationTurn]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    try: from pyannote.audio import Pipeline
    except ImportError as exc: raise RuntimeError("pyannote.audio is not installed") from exc
    ref = str(Path(config.local_model_path).expanduser()) if config.local_model_path else config.model
    pipeline = Pipeline.from_pretrained(ref)
    annotation = pipeline(audio_path)
    raw = [DiarizationTurn(float(turn.start), float(turn.end), str(label)) for turn, _, label in annotation.itertracks(yield_label=True)]
    names, normalized = {}, []
    for turn in raw:
        names.setdefault(turn.speaker, f"SPEAKER_{len(names):02d}")
        normalized.append(DiarizationTurn(turn.start, turn.end, names[turn.speaker]))
    return normalized
def _energy_cluster_diarize(audio_path: str, max_speakers: int) -> list[DiarizationTurn]:
    """Cluster 1-second acoustic frames; baseline only, not a pyannote replacement."""
    try: import soundfile as sf
    except ImportError as exc: raise RuntimeError("soundfile is required for energy fallback") from exc
    audio, rate = sf.read(audio_path, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1: audio = np.mean(audio, axis=1)
    if len(audio) == 0: return []
    size, hop = max(1, int(rate)), max(1, int(rate * .5))
    features, times = [], []
    for start in range(0, max(1, len(audio) - size + 1), hop):
        frame = audio[start:start + size]
        if len(frame) < size // 2: continue
        rms = float(np.sqrt(np.mean(frame * frame) + 1e-10))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(frame))))) if len(frame) > 1 else 0.0
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(len(frame))))
        freqs = np.fft.rfftfreq(len(frame), 1 / rate)
        centroid = float((spectrum * freqs).sum() / (spectrum.sum() + 1e-8)) / rate
        features.append([math.log(rms + 1e-5), zcr, centroid])
        times.append((start / rate, min(len(audio) / rate, (start + size) / rate)))
    if not features: return []
    x = np.asarray(features, dtype=np.float32)
    active = np.where(x[:, 0] > np.percentile(x[:, 0], 20))[0]
    if len(active) < 2: return [DiarizationTurn(0.0, len(audio) / rate, "SPEAKER_00")]
    k = min(max(1, max_speakers), max(1, min(3, len(active) // 8)))
    labels = _kmeans(x[active], k)
    frame_labels = np.full(len(x), -1, dtype=int); frame_labels[active] = labels
    names, turns, current = {}, [], None
    for idx, cluster in enumerate(frame_labels):
        if cluster < 0: continue
        names.setdefault(int(cluster), f"SPEAKER_{len(names):02d}")
        speaker, start, end = names[int(cluster)], *times[idx]
        if current and current.speaker == speaker and start <= current.end + .55: current.end = end
        else:
            if current: turns.append(current)
            current = DiarizationTurn(start, end, speaker)
    if current: turns.append(current)
    return turns
def _kmeans(x: np.ndarray, k: int, iterations: int = 20) -> np.ndarray:
    scaled = (x - x.mean(axis=0)) / (x.std(axis=0) + 1e-6)
    centers = scaled[np.linspace(0, len(scaled) - 1, k, dtype=int)].copy(); labels = np.zeros(len(scaled), dtype=int)
    for _ in range(iterations):
        distances = ((scaled[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new = distances.argmin(axis=1)
        if np.array_equal(labels, new): break
        labels = new
        for i in range(k):
            members = scaled[labels == i]
            if len(members): centers[i] = members.mean(axis=0)
    return labels
def annotate_segments(segments: Iterable[TranscriptSegment], turns: list[DiarizationTurn]) -> list[TranscriptSegment]:
    result = []
    for segment in segments:
        speaker, best = "SPEAKER_00", 0.0
        for turn in turns:
            overlap = max(0.0, min(segment.end, turn.end) - max(segment.start, turn.start))
            if overlap > best: speaker, best = turn.speaker, overlap
        result.append(TranscriptSegment(segment.start, segment.end, segment.text, speaker))
    return result
