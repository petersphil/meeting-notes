"""Read optional anonymous-speaker to real-name mappings."""
import json
from pathlib import Path
def load_speaker_map(path: str | Path | None) -> dict[str, str]:
    if not path: return {}
    p = Path(path); text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict): raise ValueError("Speaker map JSON must be an object")
        return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip() and str(v).strip()}
    result = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"): continue
        if "=" in line: key, value = line.split("=", 1)
        elif ":" in line: key, value = line.split(":", 1)
        else: raise ValueError(f"Invalid speaker map line {lineno}: expected KEY = NAME")
        if key.strip() and value.strip(): result[key.strip()] = value.strip()
    return result
def display_speaker(speaker: str, mapping: dict[str, str]) -> str:
    return mapping.get(speaker, speaker)
