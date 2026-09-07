"""End-to-end local meeting processing."""
from pathlib import Path
import json, shutil
from .diarize import annotate_segments, diarize
from .formatting import actions_markdown, transcript_json, transcript_markdown
from .offline import enforce_offline_policy
from .preprocess import preprocess_audio
from .speaker_map import load_speaker_map
from .summarize import generate_notes
from .whisper import transcribe
def process_meeting(audio_path, config, output_root=None, speaker_map_path=None, keep_work=False) -> Path:
    source = Path(audio_path).expanduser().resolve()
    if not source.is_file(): raise FileNotFoundError(source)
    enforce_offline_policy(config.summary.ollama_url)
    root = Path(output_root or config.output.root).expanduser().resolve(); meeting_dir = root / source.stem
    meeting_dir.mkdir(parents=True, exist_ok=True); work_dir = meeting_dir / ".work"
    local_audio = preprocess_audio(source, work_dir)
    segments, metadata = transcribe(str(local_audio), config.transcription)
    turns = diarize(str(local_audio), config.diarization); segments = annotate_segments(segments, turns)
    names = load_speaker_map(speaker_map_path)
    (meeting_dir / "transcript.md").write_text(transcript_markdown(segments, names), encoding="utf-8")
    metadata.update({"audio": str(source), "offline": True, "speaker_map": names, "diarization_method": config.diarization.method, "speaker_turns": [t.__dict__ for t in turns]})
    (meeting_dir / "transcript.json").write_text(transcript_json(segments, metadata), encoding="utf-8")
    try: full, short, actions = generate_notes(segments, config.summary)
    except Exception as exc:
        full = f"# Summary unavailable\n\nLocal summarization could not run: `{exc}`\n\nThe transcript was generated successfully. Start local Ollama and rerun."
        short, actions = "Summary unavailable; see transcript.md.", []
    (meeting_dir / "summary_full.md").write_text("# Full summary\n\n" + full.strip() + "\n", encoding="utf-8")
    (meeting_dir / "summary_short.md").write_text("# Short summary\n\n" + short.strip() + "\n", encoding="utf-8")
    (meeting_dir / "actions.md").write_text(actions_markdown(actions), encoding="utf-8")
    (meeting_dir / "actions.json").write_text(json.dumps([a.to_dict() for a in actions], indent=2) + "\n", encoding="utf-8")
    if not keep_work: shutil.rmtree(work_dir, ignore_errors=True)
    return meeting_dir
