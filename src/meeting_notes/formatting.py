"""Stable Markdown and JSON output formatting."""
import json
from .speaker_map import display_speaker
def timestamp(seconds: float) -> str:
    whole = max(0, int(seconds)); return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}"
def transcript_markdown(segments, speaker_map=None) -> str:
    mapping = speaker_map or {}; lines = ["# Transcript", "", "_Generated locally; no audio or text leaves this computer._", ""]
    for segment in segments:
        lines += [f"**[{timestamp(segment.start)}–{timestamp(segment.end)}] {display_speaker(segment.speaker, mapping)}:** {segment.text}", ""]
    return "\n".join(lines).rstrip() + "\n"
def transcript_json(segments, metadata: dict) -> str:
    return json.dumps({"offline": True, "metadata": metadata, "segments": [s.to_dict() for s in segments]}, indent=2, ensure_ascii=False) + "\n"
def actions_markdown(actions) -> str:
    lines = ["# Action items", "", "_Generated locally; verify owners and dates against the recording._", ""]
    if not actions: lines.append("No action items were confidently extracted.")
    for a in actions: lines.append(f"- [ ] {a.action} — **Owner:** {a.owner}; **Due:** {a.due}" + (f"; **Source:** {a.source}" if a.source else ""))
    return "\n".join(lines).rstrip() + "\n"
