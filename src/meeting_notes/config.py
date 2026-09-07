"""TOML configuration with conservative offline defaults."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os, tomllib
@dataclass
class TranscriptionConfig:
    model: str = "small.en"
    device: str = "auto"
    compute_type: str = "int8"
    language: str = "en"
    beam_size: int = 5
@dataclass
class DiarizationConfig:
    method: str = "auto"
    model: str = "pyannote/speaker-diarization-3.1"
    local_model_path: str = ""
    max_speakers: int = 8
@dataclass
class SummaryConfig:
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    language: str = "en-CA"
    temperature: float = 0.2
@dataclass
class OutputConfig:
    root: str = "outputs"
@dataclass
class AppConfig:
    transcription: TranscriptionConfig
    diarization: DiarizationConfig
    summary: SummaryConfig
    output: OutputConfig
def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}
def load_config(path: str | Path | None = None) -> AppConfig:
    raw = {}
    if path:
        with Path(path).open("rb") as f: raw = tomllib.load(f)
    sections = [_section(raw, n) for n in ("transcription", "diarization", "summary", "output")]
    classes = [TranscriptionConfig, DiarizationConfig, SummaryConfig, OutputConfig]
    values = [cls(**{k: section[k] for k in cls.__dataclass_fields__ if k in section}) for cls, section in zip(classes, sections)]
    summary = values[2]
    summary.ollama_url = os.getenv("MEETING_NOTES_OLLAMA_URL", summary.ollama_url)
    summary.ollama_model = os.getenv("MEETING_NOTES_OLLAMA_MODEL", summary.ollama_model)
    return AppConfig(*values)
