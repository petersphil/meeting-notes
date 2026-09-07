"""Local audio normalization through ffmpeg."""
from pathlib import Path
import shutil, subprocess
SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a"}
def preprocess_audio(source: str | Path, work_dir: str | Path) -> Path:
    source = Path(source)
    if not source.is_file(): raise FileNotFoundError(source)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES: raise ValueError("Use wav, mp3, or m4a audio")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("ffmpeg is required and must be on PATH")
    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    target = work / "audio_16khz_mono.wav"
    cmd = [ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(target)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode: raise RuntimeError(f"ffmpeg failed: {done.stderr[-2000:]}")
    return target
