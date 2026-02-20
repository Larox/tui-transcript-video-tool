# TUI Video-to-Docs

Terminal UI application that transcribes video files using Deepgram and exports each transcription to Google Docs or local Markdown files.

## Prerequisites

- [mise](https://mise.jdx.dev/) and [uv](https://docs.astral.sh/uv/)
- A Deepgram API key ([get one here](https://console.deepgram.com/))
- (Optional) A Google Cloud service account JSON key with Drive + Docs API enabled

## Setup

```bash
# Install Python and create venv via mise
mise install

# Install dependencies
uv sync

# Copy and fill in your credentials
cp .env.example .env
```

## Usage

```bash
uv run tui-transcript
```

1. Enter your Deepgram API key on the config screen.
2. Optionally provide Google service account JSON path and Drive folder ID.
3. Add video files and press **Start** to transcribe.

If Google credentials are not provided, transcriptions are saved as `.md` files in the output directory.
