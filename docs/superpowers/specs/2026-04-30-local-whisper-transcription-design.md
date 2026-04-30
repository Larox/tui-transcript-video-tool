# Local Whisper Transcription — Design Spec

**Date:** 2026-04-30
**Status:** Approved (pending implementation plan)
**Branch (proposed):** `feature/local-whisper`

## Summary

Add a second transcription engine — local Whisper via `faster-whisper` — alongside the existing Deepgram backend. Users select engine + model per-job from the Transcribe view. Local models are managed (downloaded / removed) from a new section in Settings.

## Goals

- Eliminate hard dependency on Deepgram for transcription.
- Let the user choose, per job, which engine to use and which Whisper model size.
- Keep the existing pipeline, key-moments extraction, history, search, and export flows working unchanged.
- Cross-platform install (no native compile step).

## Non-Goals

- Speaker diarization for the local engine (Deepgram keeps it; local does not).
- A global default-engine setting (per-job only in v1).
- Concurrent local transcriptions (jobs already run serially).
- Word-level timestamps (paragraph-level matches current Deepgram output shape).

## User-facing UX

### Transcribe view
- New "Engine" select next to the Class selector: **Deepgram** (default) | **Local Whisper**.
- When Local is selected, a "Model" select appears, populated from `GET /api/models/local` filtered to `downloaded=true`.
- If no local models are downloaded, the Model select is empty and a helper link points to Settings.

### Settings — Local models section
- Lists each available model with: name, size on disk, downloaded? status.
- Download button per row → triggers SSE-streamed download with a progress bar.
- Remove button per row → deletes the model from the Hugging Face cache.

## Architecture

### New package layout

Replace the single `services/transcription.py` with a package:

```
services/transcription/
  __init__.py          # public API: transcribe(), get_transcriber()
  base.py              # Transcriber Protocol, shared dataclasses
  deepgram.py          # existing Deepgram logic, refactored into DeepgramTranscriber
  whisper_local.py     # new: WhisperTranscriber using faster-whisper
  models.py            # local model registry + HF cache management
```

`services/transcription/__init__.py` keeps the same `transcribe(...)` symbol used by tests for backward compat during refactor; the pipeline migrates to `get_transcriber(engine, model).transcribe(...)`.

### Transcriber protocol (`base.py`)

```python
class Transcriber(Protocol):
    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str,
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult: ...
```

`TranscriptResult` and `TranscriptParagraph` keep their current shape (already in `models.py`). Both engines emit the same type.

### Engine selection

```python
def get_transcriber(engine: str, *, model: str | None, deepgram_api_key: str | None) -> Transcriber: ...
```

- `engine="deepgram"` → returns `DeepgramTranscriber(api_key)`.
- `engine="whisper_local"` → returns `WhisperTranscriber(model_name)`.

## Whisper transcriber (`whisper_local.py`)

1. Reuse existing ffmpeg path to extract mono 16 kHz WAV from video files. Audio inputs go straight through.
2. Load `faster_whisper.WhisperModel(model_name, device="auto", compute_type="auto")`. Cache the loaded model in a module-level dict keyed by `model_name` to avoid 5–10s reload per job.
3. Run `model.transcribe(wav_path, language=lang_or_none, vad_filter=True, beam_size=5)` inside `asyncio.to_thread` (faster-whisper is sync).
4. Aggregate streaming segments into `TranscriptParagraph` chunks. Strategy: start a new paragraph when the gap between two consecutive segments exceeds 1.5 seconds (silence break) OR when the current paragraph reaches 8 segments — whichever comes first. Each `TranscriptParagraph` gets `start = first_segment.start`, `end = last_segment.end`, `text = " ".join(segment_texts)`. This produces output matching Deepgram's paragraph shape so downstream Key Moments extraction works unchanged.
5. Push `on_status` updates with `current_timestamp / total_duration` so the UI sees progress.
6. Return `TranscriptResult(text=full_text, paragraphs=[...])`.

**Language handling:** `"multi"` (auto-detect) → pass `None` to faster-whisper. Other BCP-47 codes pass through unchanged.

## Local model registry (`models.py`)

```python
LOCAL_MODELS = {
    "small":    ("Systran/faster-whisper-small",    466),
    "medium":   ("Systran/faster-whisper-medium",   1530),
    "large-v3": ("Systran/faster-whisper-large-v3", 3090),
}  # size in MB

def list_models() -> list[ModelInfo]: ...        # name, size_mb, downloaded
def is_downloaded(name: str) -> bool: ...        # via huggingface_hub.scan_cache_dir
async def download(name: str, on_progress: Callable[[int], None]) -> None: ...
async def remove(name: str) -> None: ...
```

Uses `huggingface_hub.snapshot_download` for fetching and `huggingface_hub.scan_cache_dir` / `delete_repo_cache` for inspection and removal.

## API changes

### `api/schemas.py`
```python
class TranscriptionStartRequest(BaseModel):
    # existing fields...
    engine: Literal["deepgram", "whisper_local"] = "deepgram"
    whisper_model: Literal["small", "medium", "large-v3"] | None = None
```

Validation rules (in the route, after pydantic):
- `engine == "whisper_local"` requires `whisper_model`.
- `engine == "whisper_local"` requires the named model to be downloaded (`models.is_downloaded`).
- `engine == "deepgram"` requires `config.deepgram_api_key`.
- Violations → `400` with a clear message.

### `VideoJob` (`models.py`)
Add `engine: str` and `whisper_model: str | None` so the pipeline can read them per-job.

### New routes — `api/routes/models.py`
- `GET    /api/models/local` → `[{name, downloaded, size_mb}]`
- `POST   /api/models/local/{name}/download` → SSE stream emitting `{progress: 0..100}` events; final `done` or `error` event.
- `DELETE /api/models/local/{name}` → 204 on success.

## Pipeline changes (`services/pipeline.py`)

Inside the per-job loop, replace the direct call to `transcribe(config.deepgram_api_key, ...)` with:

```python
transcriber = get_transcriber(
    job.engine,
    model=job.whisper_model,
    deepgram_api_key=config.deepgram_api_key,
)
transcript_result = await transcriber.transcribe(
    job.path, language=job.language, on_status=_on_status
)
```

No other pipeline logic changes. Key Moments, history, exporter, search indexing all work off `TranscriptResult`, which is unchanged.

## Frontend changes

- `frontend/src/api/client.ts` — extend `startTranscription` with `engine` + `whisperModel`.
- New API helpers: `listLocalModels`, `downloadLocalModel` (SSE), `removeLocalModel`.
- New `EngineSelect` component used in `Dashboard.tsx` (Transcribe view).
- New `LocalModelsPanel` component added to `Config.tsx` (Settings).

## Dependency changes

`pyproject.toml` adds:
- `faster-whisper`
- `huggingface-hub`

Both are pure-Python wheels — no compile step. CTranslate2 (faster-whisper's runtime) ships prebuilt wheels for macOS/Linux/Windows.

## Error handling

| Scenario | Surface |
|----------|---------|
| `engine="whisper_local"` without `whisper_model` | 400 at route |
| Model not downloaded | 400 at route, message points to Settings |
| `faster-whisper` import fails | Caught in `get_transcriber`; job-level error: "Local Whisper not installed. Run: uv sync" |
| Download failure (network, disk) | SSE `error` event; partial cache cleaned up |
| Runtime transcribe error (OOM, corrupt audio) | Existing pipeline `try/except` marks job ERROR — same UX as Deepgram failures |

## Testing

All tests mock at the library boundary — no real model downloads or transcriptions in CI.

- `tests/test_whisper_transcriber.py` — `faster_whisper.WhisperModel` mocked; covers paragraph aggregation, `multi` → `None` language mapping, progress callbacks, output shape parity with Deepgram.
- `tests/test_models_api.py` — list / download (SSE progress) / delete; `huggingface_hub` mocked; 400 on unknown model name.
- `tests/test_transcription_directory.py` (extend) — engine validation: `whisper_local` without `whisper_model` → 400; with undownloaded model → 400.
- `tests/test_pipeline_overrides.py` (extend) — parametrized test runs `run_pipeline` once per engine with a fake `Transcriber` returning canned `TranscriptResult`; both paths produce identical `VideoJob` end-state and trigger key-moments extraction.

## Risks

- **Model load time** (5–10s for large-v3) on first job per process. Mitigated by module-level cache. Subsequent jobs in the same FastAPI process are fast.
- **Disk usage** — large-v3 is ~3 GB. Settings UI surfaces size and Remove button so users can manage.
- **Quality regression vs Deepgram on noisy audio** — `large-v3` matches Deepgram on clean speech but can underperform on heavy accents or overlapping speakers. Documented as a known tradeoff; users can fall back to Deepgram per-job.

## Out of scope (future work)

- Diarization via `pyannote.audio`.
- MLX-Whisper backend for faster M-series performance.
- Global default-engine setting in Settings.
- Streaming transcription (real-time).
