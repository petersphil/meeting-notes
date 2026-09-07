# Offline Meeting Notes

Production-oriented starter for converting local phone recordings into timestamped, speaker-labelled transcripts, summaries, and action items. **Audio, transcription, diarization, and summarization stay on the laptop.** The only HTTP request is to an Ollama server explicitly restricted to loopback (`localhost`, `127.0.0.1`, or `::1`). There are no OpenAI, Anthropic, telemetry, analytics, or cloud API clients.

## Pipeline

`meeting-notes process recording.m4a` runs: preprocess with ffmpeg; faster-whisper transcription; cached pyannote diarization (preferred) or a local energy/feature clustering fallback; timestamp/speaker annotation; local Ollama generation of full and short summaries plus action items; and Markdown/JSON output.

## Prerequisites

- Python 3.11+; `ffmpeg` on PATH (`sudo apt install ffmpeg` or `brew install ffmpeg`).
- Enough RAM/disk for your faster-whisper model. `small.en` is a practical start; `medium.en`/`large-v3` improve accuracy but require more resources.
- Local Ollama at `http://127.0.0.1:11434` for summaries.

## Install and one-time model preparation

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -e ".[test]"
```

While online, run the tool once to download the selected faster-whisper model into its local cache, or warm that cache using the model package. Then disconnect or set `HF_HUB_OFFLINE=1`. For preferred diarization:

```bash
pip install -e ".[diarization]"
```

While online, accept pyannote model terms and download/cache `pyannote/speaker-diarization-3.1` according to pyannote's current instructions (a Hugging Face token may be required only for that one-time preparation). Actual processing makes no Hugging Face request. `method = "auto"` falls back to the built-in no-download energy/feature clustering if pyannote is not installed or cached; it is less reliable with overlap/noise. Use `method = "pyannote"` to fail rather than fall back.

Prepare Ollama once online, then keep it local:

```bash
ollama pull llama3.1:8b
ollama serve
```

The application sends prompts only to that local Ollama process.

## Phone workflow and usage

Transfer the original `.wav`, `.mp3`, or `.m4a` from the phone by USB or another local method, disconnect from the network if desired, then:

```bash
cp meeting-notes.example.toml meeting-notes.toml
meeting-notes process ./recording.m4a --config meeting-notes.toml
```

Overrides:

```bash
meeting-notes process meeting.wav --output-dir ./outputs \
  --speaker-map speakers.json --whisper-model small.en \
  --diarization-method energy --ollama-model llama3.1:8b
```

Speaker map JSON: `{"SPEAKER_00": "Phil Peters", "SPEAKER_01": "Alex Wong"}`. Plain text also works (`SPEAKER_00 = Phil Peters` or `SPEAKER_01: Alex Wong`); comments and blank lines are ignored.

Default output is `outputs/<recording-stem>/` (or the supplied output root):
`transcript.md`, `transcript.json`, `summary_full.md`, `summary_short.md`, `actions.md`, and `actions.json`.

## Hardware and limitations

Three hours may take minutes to several hours depending on model, CPU/GPU, and quantization. `cpu`/`int8` is broadly compatible; CUDA is faster when configured. Pyannote is preferred for diarization; the fallback clusters 1-second acoustic frames and cannot robustly identify overlapping speakers or know the true speaker count. Labels remain anonymous without a map. Ollama must already be running; if it is unavailable, transcript artifacts are still written and summaries contain an actionable error. No automatic network download is attempted. Generated notes must be verified against the recording.

## Development

```bash
pytest -q
python -m meeting_notes.cli --help
```

For an intentional one-time online cache warm-up only, set `MEETING_NOTES_ALLOW_MODEL_DOWNLOAD=1` while using a local model command, then unset it before processing. Normal execution sets `HF_HUB_OFFLINE=1` before model loading and fails fast if a cache is missing.

Example faster-whisper cache warm-up while intentionally online (run once, then disconnect):

```bash
MEETING_NOTES_ALLOW_MODEL_DOWNLOAD=1 python -c 'from faster_whisper import WhisperModel; WhisperModel("small.en", device="cpu", compute_type="int8")'
```
