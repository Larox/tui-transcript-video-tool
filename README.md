# TUI Video-to-Docs

Terminal UI and web API for transcribing video/audio files using Deepgram and exporting to Google Docs or local Markdown files.

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

### TUI (Terminal)

```bash
uv run tui-transcript
```

1. Enter your Deepgram API key on the config screen.
2. Optionally provide Google service account JSON path and Drive folder ID.
3. Add video files and press **Start** to transcribe.

If Google credentials are not provided, transcriptions are saved as `.md` files in the output directory.

### Web API

```bash
uv run tui-transcript-api
```

Starts the FastAPI server at `http://localhost:8000`. See [API docs](http://localhost:8000/docs).

### React Frontend

```bash
# Install Node via mise (if not already)
mise install

# Start the API first (in one terminal)
uv run tui-transcript-api

# Start the frontend (in another terminal)
cd frontend && npm run dev
```

Open `http://localhost:5173`. The frontend proxies API requests to the backend.

**API Endpoints:**
- `GET /api/config` – Get config (API key masked)
- `PUT /api/config` – Update config
- `POST /api/files/upload` – Upload video/audio files (multipart)
- `POST /api/transcription/start` – Start transcription
- `GET /api/transcription/progress/{session_id}` – SSE stream of progress
