"""Command-line interface."""
import argparse
import sys

from .config import load_config
from .offline import offline_status
from .pipeline import process_meeting


def build_parser():
    parser = argparse.ArgumentParser(prog='meeting-notes', description='Offline transcription, diarization, and local meeting notes')
    sub = parser.add_subparsers(dest='command', required=True)
    process = sub.add_parser('process', help='process local audio')
    process.add_argument('audio')
    process.add_argument('--config')
    process.add_argument('--output-dir')
    process.add_argument('--speaker-map')
    process.add_argument('--whisper-model')
    process.add_argument('--diarization-method', choices=['auto', 'pyannote', 'energy'])
    process.add_argument('--ollama-model')
    process.add_argument('--keep-work', action='store_true')
    serve = sub.add_parser('serve', help='serve the local browser UI and API')
    serve.add_argument('--host', default='127.0.0.1', help='localhost bind address (default: 127.0.0.1)')
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--config')
    serve.add_argument('--jobs-dir', default='.meeting-notes/jobs', help='local upload/output directory')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'process':
        try:
            config = load_config(args.config)
            if args.whisper_model: config.transcription.model = args.whisper_model
            if args.diarization_method: config.diarization.method = args.diarization_method
            if args.ollama_model: config.summary.ollama_model = args.ollama_model
            print(offline_status())
            output = process_meeting(args.audio, config, args.output_dir, args.speaker_map, args.keep_work)
            print(f'Wrote meeting artifacts to {output}')
            return 0
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
    if args.command == 'serve':
        try:
            from .web import run_server
            run_server(args.host, args.port, args.config, args.jobs_dir)
            return 0
        except Exception as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
