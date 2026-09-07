"""Command-line interface."""
import argparse, sys
from .config import load_config
from .offline import offline_status
from .pipeline import process_meeting
def build_parser():
    parser = argparse.ArgumentParser(prog="meeting-notes", description="Offline transcription, diarization, and local meeting notes")
    sub = parser.add_subparsers(dest="command", required=True); p = sub.add_parser("process", help="process local wav/mp3/m4a")
    p.add_argument("audio"); p.add_argument("--config"); p.add_argument("--output-dir"); p.add_argument("--speaker-map")
    p.add_argument("--whisper-model"); p.add_argument("--diarization-method", choices=["auto", "pyannote", "energy"]); p.add_argument("--ollama-model"); p.add_argument("--keep-work", action="store_true")
    return parser
def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "process":
        try:
            config = load_config(args.config)
            if args.whisper_model: config.transcription.model = args.whisper_model
            if args.diarization_method: config.diarization.method = args.diarization_method
            if args.ollama_model: config.summary.ollama_model = args.ollama_model
            print(offline_status()); output = process_meeting(args.audio, config, args.output_dir, args.speaker_map, args.keep_work)
            print(f"Wrote meeting artifacts to {output}"); return 0
        except Exception as exc: print(f"error: {exc}", file=sys.stderr); return 2
    return 2
if __name__ == "__main__": raise SystemExit(main())
