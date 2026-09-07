"""faster-whisper adapter with offline model-cache enforcement."""
from dataclasses import dataclass, asdict
from typing import Any
import os
@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str = "SPEAKER_00"
    def to_dict(self) -> dict[str, Any]: return asdict(self)
def transcribe(audio_path: str, config) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    if os.getenv("MEETING_NOTES_ALLOW_MODEL_DOWNLOAD") != "1": os.environ["HF_HUB_OFFLINE"] = "1"
    try: from faster_whisper import WhisperModel
    except ImportError as exc: raise RuntimeError("Install faster-whisper before processing audio") from exc
    device = config.device
    if device == "auto": device = "cuda" if _cuda_available() else "cpu"
    model = WhisperModel(config.model, device=device, compute_type=config.compute_type)
    segments, info = model.transcribe(audio_path, language=config.language, beam_size=config.beam_size, vad_filter=True, condition_on_previous_text=True)
    result = [TranscriptSegment(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]
    return result, {"language": getattr(info, "language", config.language), "language_probability": getattr(info, "language_probability", None), "model": config.model, "device": device}
def _cuda_available() -> bool:
    try:
        import ctranslate2
        return bool(ctranslate2.get_cuda_device_count())
    except Exception: return False
