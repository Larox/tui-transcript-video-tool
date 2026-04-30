# Local Whisper Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second transcription engine (local Whisper via `faster-whisper`) alongside the existing Deepgram backend, with per-job engine + model selection and a Settings panel for managing local model downloads.

**Architecture:** Refactor `services/transcription.py` (single file) into a package with a `Transcriber` Protocol and two implementations (`DeepgramTranscriber`, `WhisperTranscriber`). The pipeline picks an implementation per job via `get_transcriber()`. Local model download/cache is exposed through new `/api/models/local` routes. Both engines emit the same `TranscriptResult` so downstream stages (key moments, export, search) are untouched.

**Tech Stack:** Python 3.12, FastAPI, faster-whisper, huggingface-hub, pytest. React 19, TypeScript, Vite, TanStack Query, shadcn/ui.

**Spec:** [docs/superpowers/specs/2026-04-30-local-whisper-transcription-design.md](../specs/2026-04-30-local-whisper-transcription-design.md)

**Branch:** `feature/local-whisper-impl` (already created from `main` with the spec cherry-picked)

---

## File Structure

**New files:**
- `src/tui_transcript/services/transcription/__init__.py` — re-exports for back-compat (`transcribe`, `get_transcriber`)
- `src/tui_transcript/services/transcription/base.py` — `Transcriber` Protocol, `TranscriberError`
- `src/tui_transcript/services/transcription/deepgram.py` — `DeepgramTranscriber` (current logic, refactored)
- `src/tui_transcript/services/transcription/whisper_local.py` — `WhisperTranscriber` (faster-whisper)
- `src/tui_transcript/services/transcription/models.py` — local model registry + HF cache helpers
- `src/tui_transcript/api/routes/models.py` — list/download/delete endpoints
- `tests/test_whisper_transcriber.py`
- `tests/test_local_models.py`
- `tests/test_models_api.py`
- `frontend/src/components/EngineSelect.tsx`
- `frontend/src/components/LocalModelsPanel.tsx`

**Deleted:**
- `src/tui_transcript/services/transcription.py` (replaced by the package)

**Modified:**
- `pyproject.toml` — add `faster-whisper`, `huggingface-hub`
- `src/tui_transcript/models.py` — `VideoJob` gets `engine`, `whisper_model`
- `src/tui_transcript/services/pipeline.py` — call `get_transcriber()` instead of direct `transcribe()`
- `src/tui_transcript/api/schemas.py` — `FileSpec` gets `engine`, `whisper_model`
- `src/tui_transcript/api/routes/transcription.py` — validation + pass through to `VideoJob`
- `src/tui_transcript/api/main.py` — register `models` router
- `tests/test_pipeline_overrides.py` — extend with engine parametrization
- `tests/test_transcription_directory.py` — extend with engine validation cases
- `frontend/src/api/client.ts` — engine fields on `FileSpec`, new model endpoints
- `frontend/src/pages/Dashboard.tsx` — integrate `EngineSelect`
- `frontend/src/pages/Config.tsx` — integrate `LocalModelsPanel`

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Edit the `dependencies` array to include `faster-whisper` and `huggingface-hub`:

```toml
[project]
name = "tui-transcript"
version = "0.1.0"
description = "TUI app to transcribe video files via Deepgram and export to Markdown"
requires-python = ">=3.12"
dependencies = [
    "textual",
    "deepgram-sdk",
    "python-dotenv",
    "fastapi",
    "uvicorn[standard]",
    "python-multipart",
    "anthropic>=0.25",
    "faster-whisper>=1.0",
    "huggingface-hub>=0.24",
]
```

- [ ] **Step 2: Sync deps**

Run: `uv sync`
Expected: prints "Resolved … packages" then "Installed … packages" with `faster-whisper` and `huggingface-hub` in the list.

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "import faster_whisper, huggingface_hub; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "Add faster-whisper and huggingface-hub deps"
```

---

## Task 2: Create transcription package skeleton + Protocol

**Files:**
- Create: `src/tui_transcript/services/transcription/__init__.py`
- Create: `src/tui_transcript/services/transcription/base.py`
- Test: `tests/test_transcriber_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_transcriber_protocol.py`:

```python
"""Verify the Transcriber Protocol shape."""
from __future__ import annotations

import inspect
from pathlib import Path

from tui_transcript.services.transcription.base import (
    Transcriber,
    TranscriberError,
)
from tui_transcript.models import TranscriptResult


def test_transcriber_protocol_has_transcribe_method():
    assert hasattr(Transcriber, "transcribe")


def test_transcriber_error_is_exception():
    assert issubclass(TranscriberError, Exception)


class _FakeTranscriber:
    async def transcribe(self, file_path, *, language, on_status=None):
        return TranscriptResult(text="hi", paragraphs=[])


def test_concrete_class_satisfies_protocol():
    t: Transcriber = _FakeTranscriber()  # structural typing
    sig = inspect.signature(t.transcribe)
    assert "file_path" in sig.parameters
    assert "language" in sig.parameters
    assert "on_status" in sig.parameters
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transcriber_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tui_transcript.services.transcription.base'`.

- [ ] **Step 3: Create the package + base module**

Create `src/tui_transcript/services/transcription/__init__.py`:

```python
"""Transcription engines. Public API: get_transcriber, Transcriber, TranscriberError."""
from __future__ import annotations

from tui_transcript.services.transcription.base import (
    Transcriber,
    TranscriberError,
)

__all__ = ["Transcriber", "TranscriberError", "get_transcriber"]


def get_transcriber(
    engine: str,
    *,
    model: str | None = None,
    deepgram_api_key: str | None = None,
) -> Transcriber:
    """Return a Transcriber for the requested engine.

    engine: "deepgram" | "whisper_local"
    model: required when engine == "whisper_local" (e.g. "large-v3")
    """
    if engine == "deepgram":
        if not deepgram_api_key:
            raise TranscriberError("Deepgram API key is required for engine='deepgram'")
        from tui_transcript.services.transcription.deepgram import DeepgramTranscriber
        return DeepgramTranscriber(deepgram_api_key)
    if engine == "whisper_local":
        if not model:
            raise TranscriberError("model is required for engine='whisper_local'")
        from tui_transcript.services.transcription.whisper_local import (
            WhisperTranscriber,
        )
        return WhisperTranscriber(model)
    raise TranscriberError(f"Unknown engine: {engine}")
```

Create `src/tui_transcript/services/transcription/base.py`:

```python
"""Transcriber Protocol and shared error type."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from tui_transcript.models import TranscriptResult


class TranscriberError(Exception):
    """Raised when a transcriber cannot run (bad config, missing model, etc.)."""


class Transcriber(Protocol):
    """Common interface for transcription engines."""

    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str,
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_transcriber_protocol.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/transcription/__init__.py src/tui_transcript/services/transcription/base.py tests/test_transcriber_protocol.py
git commit -m "Add Transcriber Protocol and engine selector"
```

---

## Task 3: Move Deepgram into the package

**Files:**
- Create: `src/tui_transcript/services/transcription/deepgram.py`
- Delete: `src/tui_transcript/services/transcription.py`

- [ ] **Step 1: Create the deepgram module**

Create `src/tui_transcript/services/transcription/deepgram.py`. This is the existing single-file logic refactored into a class:

```python
"""Deepgram-backed transcriber."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from deepgram import AsyncDeepgramClient

from tui_transcript.models import TranscriptParagraph, TranscriptResult

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".opus", ".wma"}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_audio(video_path: Path, out_path: Path) -> None:
    """Use ffmpeg to extract a mono 16 kHz WAV — optimal for Deepgram + Whisper."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


class DeepgramTranscriber:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str = "es",
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult:
        def _notify(msg: str) -> None:
            if on_status:
                on_status(msg)

        use_ffmpeg = not _is_audio_file(file_path) and _has_ffmpeg()
        tmp_dir = None

        try:
            if use_ffmpeg:
                _notify("Extracting audio track (ffmpeg)...")
                tmp_dir = tempfile.mkdtemp(prefix="tui_transcript_")
                wav_path = Path(tmp_dir) / "audio.wav"
                await asyncio.to_thread(_extract_audio, file_path, wav_path)
                source_path = wav_path
                _notify(
                    f"Audio extracted: {wav_path.stat().st_size / 1_048_576:.1f} MB"
                )
            else:
                source_path = file_path
                size_mb = file_path.stat().st_size / 1_048_576
                if use_ffmpeg is False and not _is_audio_file(file_path):
                    _notify(
                        f"ffmpeg not found — sending raw video ({size_mb:.0f} MB). "
                        "Install ffmpeg for faster uploads."
                    )
                else:
                    _notify(f"Sending audio file ({size_mb:.1f} MB)...")

            _notify("Uploading to Deepgram...")
            audio_bytes = await asyncio.to_thread(source_path.read_bytes)

            client = AsyncDeepgramClient(api_key=self._api_key)
            response = await client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                model="nova-3",
                language=language,
                smart_format=True,
                paragraphs=True,
                diarize=True,
                request_options={"timeout_in_seconds": 600},
            )

            alt = response.results.channels[0].alternatives[0]

            paragraphs: list[TranscriptParagraph] = []
            if alt.paragraphs and alt.paragraphs.paragraphs:
                for para in alt.paragraphs.paragraphs:
                    sentence_texts = [s.text for s in (para.sentences or [])]
                    paragraphs.append(
                        TranscriptParagraph(
                            start=para.start,
                            end=para.end,
                            text=" ".join(sentence_texts),
                        )
                    )

            if alt.paragraphs and alt.paragraphs.transcript:
                return TranscriptResult(
                    text=alt.paragraphs.transcript, paragraphs=paragraphs
                )

            return TranscriptResult(text=alt.transcript or "", paragraphs=paragraphs)

        finally:
            if tmp_dir is not None:
                await asyncio.to_thread(shutil.rmtree, tmp_dir, True)
```

- [ ] **Step 2: Update `__init__.py` to keep back-compat `transcribe()` symbol**

Append to `src/tui_transcript/services/transcription/__init__.py`:

```python


# Back-compat: existing tests / TUI may import `transcribe` directly.
async def transcribe(api_key: str, file_path, *, language: str = "es", on_status=None):
    """Back-compat shim — delegates to DeepgramTranscriber."""
    from tui_transcript.services.transcription.deepgram import DeepgramTranscriber
    return await DeepgramTranscriber(api_key).transcribe(
        file_path, language=language, on_status=on_status
    )
```

- [ ] **Step 3: Delete the old single-file module**

Run: `rm src/tui_transcript/services/transcription.py`

- [ ] **Step 4: Run the existing test suite**

Run: `uv run pytest -q`
Expected: all previously-passing tests still pass (no behavior change yet).

- [ ] **Step 5: Commit**

```bash
git add -u src/tui_transcript/services/transcription.py
git add src/tui_transcript/services/transcription/deepgram.py src/tui_transcript/services/transcription/__init__.py
git commit -m "Move Deepgram into transcription package"
```

---

## Task 4: Local model registry

**Files:**
- Create: `src/tui_transcript/services/transcription/models.py`
- Test: `tests/test_local_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_local_models.py`:

```python
"""Tests for the local Whisper model registry."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tui_transcript.services.transcription import models as m


def test_list_models_returns_all_known_models():
    with patch.object(m, "is_downloaded", return_value=False):
        result = m.list_models()
    names = [info["name"] for info in result]
    assert names == ["small", "medium", "large-v3"]
    assert all(info["downloaded"] is False for info in result)
    assert all(info["size_mb"] > 0 for info in result)


def test_is_downloaded_true_when_repo_in_cache():
    fake_repo = MagicMock(repo_id="Systran/faster-whisper-small")
    fake_cache = MagicMock(repos=[fake_repo])
    with patch.object(m, "scan_cache_dir", return_value=fake_cache):
        assert m.is_downloaded("small") is True


def test_is_downloaded_false_when_repo_missing():
    fake_cache = MagicMock(repos=[])
    with patch.object(m, "scan_cache_dir", return_value=fake_cache):
        assert m.is_downloaded("small") is False


def test_is_downloaded_unknown_model_returns_false():
    assert m.is_downloaded("nonexistent") is False


@pytest.mark.asyncio
async def test_download_calls_snapshot_download(monkeypatch):
    called = {}

    def fake_snapshot(repo_id, **kwargs):
        called["repo_id"] = repo_id
        return "/fake/path"

    monkeypatch.setattr(m, "snapshot_download", fake_snapshot)
    await m.download("small")
    assert called["repo_id"] == "Systran/faster-whisper-small"


@pytest.mark.asyncio
async def test_remove_calls_delete_repo(monkeypatch):
    deleted = {}

    class FakeStrategy:
        def execute(self):
            deleted["executed"] = True

    fake_repo = MagicMock(repo_id="Systran/faster-whisper-small")
    fake_repo.delete.return_value = FakeStrategy()
    fake_cache = MagicMock(repos=[fake_repo])

    monkeypatch.setattr(m, "scan_cache_dir", lambda: fake_cache)
    await m.remove("small")
    assert deleted == {"executed": True}


@pytest.mark.asyncio
async def test_remove_unknown_model_raises():
    with pytest.raises(ValueError):
        await m.remove("nonexistent")
```

- [ ] **Step 2: Add `pytest-asyncio` config (if not already enabled)**

Check `pyproject.toml`. If `[tool.pytest.ini_options]` exists, ensure `asyncio_mode = "auto"`. If not, append:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

And add `pytest-asyncio` to dev deps:

```toml
[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "pytest>=9.0.3",
    "pytest-asyncio>=0.23",
]
```

Run: `uv sync`

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_local_models.py -v`
Expected: FAIL — `models` module not found / functions undefined.

- [ ] **Step 4: Create the registry**

Create `src/tui_transcript/services/transcription/models.py`:

```python
"""Local Whisper model registry — wraps Hugging Face cache management."""
from __future__ import annotations

import asyncio
from typing import Callable

from huggingface_hub import scan_cache_dir, snapshot_download

# name -> (HF repo_id, approx size in MB)
LOCAL_MODELS: dict[str, tuple[str, int]] = {
    "small":    ("Systran/faster-whisper-small",    466),
    "medium":   ("Systran/faster-whisper-medium",   1530),
    "large-v3": ("Systran/faster-whisper-large-v3", 3090),
}


def list_models() -> list[dict]:
    """List all known local models with their download status."""
    return [
        {
            "name": name,
            "repo_id": repo_id,
            "size_mb": size_mb,
            "downloaded": is_downloaded(name),
        }
        for name, (repo_id, size_mb) in LOCAL_MODELS.items()
    ]


def is_downloaded(name: str) -> bool:
    if name not in LOCAL_MODELS:
        return False
    repo_id, _ = LOCAL_MODELS[name]
    cache = scan_cache_dir()
    return any(r.repo_id == repo_id for r in cache.repos)


async def download(
    name: str,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Download model snapshot. Blocks until complete.

    on_progress: invoked with rough percentage (0..100) — best-effort. HF's
    snapshot_download doesn't expose granular progress, so we emit 0 at start
    and 100 at end. UI should show a spinner during the gap.
    """
    if name not in LOCAL_MODELS:
        raise ValueError(f"Unknown model: {name}")
    repo_id, _ = LOCAL_MODELS[name]
    if on_progress:
        on_progress(0)
    await asyncio.to_thread(snapshot_download, repo_id)
    if on_progress:
        on_progress(100)


async def remove(name: str) -> None:
    """Delete model from HF cache."""
    if name not in LOCAL_MODELS:
        raise ValueError(f"Unknown model: {name}")
    repo_id, _ = LOCAL_MODELS[name]

    def _delete() -> None:
        cache = scan_cache_dir()
        for repo in cache.repos:
            if repo.repo_id == repo_id:
                strategy = repo.delete()
                strategy.execute()
                return

    await asyncio.to_thread(_delete)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_local_models.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/services/transcription/models.py tests/test_local_models.py pyproject.toml uv.lock
git commit -m "Add local Whisper model registry"
```

---

## Task 5: Whisper transcriber

**Files:**
- Create: `src/tui_transcript/services/transcription/whisper_local.py`
- Test: `tests/test_whisper_transcriber.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_whisper_transcriber.py`:

```python
"""Tests for WhisperTranscriber. faster-whisper is mocked."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tui_transcript.models import TranscriptResult


def _seg(start: float, end: float, text: str):
    return SimpleNamespace(start=start, end=end, text=text)


@pytest.fixture
def fake_whisper(monkeypatch):
    """Install a fake faster_whisper module with a controllable WhisperModel."""
    fake = types.ModuleType("faster_whisper")
    instance = MagicMock()
    fake.WhisperModel = MagicMock(return_value=instance)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    # Reset the module-level cache between tests
    from tui_transcript.services.transcription import whisper_local
    whisper_local._MODEL_CACHE.clear()
    return instance


@pytest.mark.asyncio
async def test_transcribe_returns_transcript_result(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00" * 1024)
    segments = iter(
        [
            _seg(0.0, 1.0, "hello"),
            _seg(1.0, 2.0, "world"),
        ]
    )
    info = SimpleNamespace(duration=2.0, language="en")
    fake_whisper.transcribe.return_value = (segments, info)

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert isinstance(result, TranscriptResult)
    assert result.text == "hello world"
    assert len(result.paragraphs) == 1
    assert result.paragraphs[0].start == 0.0
    assert result.paragraphs[0].end == 2.0


@pytest.mark.asyncio
async def test_transcribe_passes_none_for_multi_language(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="multi")
    _, kwargs = fake_whisper.transcribe.call_args
    assert kwargs["language"] is None


@pytest.mark.asyncio
async def test_transcribe_passes_language_through(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="es"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="es")
    _, kwargs = fake_whisper.transcribe.call_args
    assert kwargs["language"] == "es"


@pytest.mark.asyncio
async def test_paragraph_split_on_silence_gap(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    # Two segments with a 2.0s gap should produce two paragraphs (threshold 1.5s).
    segments = iter(
        [
            _seg(0.0, 1.0, "first"),
            _seg(3.0, 4.0, "second"),
        ]
    )
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=4.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert len(result.paragraphs) == 2
    assert result.paragraphs[0].text == "first"
    assert result.paragraphs[1].text == "second"


@pytest.mark.asyncio
async def test_paragraph_split_on_segment_count(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    # Ten consecutive close segments → must split (cap at 8 per paragraph).
    segments = iter([_seg(float(i) * 0.5, float(i) * 0.5 + 0.4, f"s{i}") for i in range(10)])
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=10.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    result = await WhisperTranscriber("small").transcribe(audio, language="en")
    assert len(result.paragraphs) == 2  # 8 + 2


@pytest.mark.asyncio
async def test_progress_callback_emits_status(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    segments = iter([_seg(0.0, 1.0, "x"), _seg(1.0, 2.0, "y")])
    fake_whisper.transcribe.return_value = (
        segments,
        SimpleNamespace(duration=2.0, language="en"),
    )

    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    statuses: list[str] = []
    await WhisperTranscriber("small").transcribe(
        audio, language="en", on_status=statuses.append
    )
    assert any("Whisper" in s or "model" in s.lower() for s in statuses)
    # Progress messages with timestamp markers were emitted:
    assert any("/" in s for s in statuses)


@pytest.mark.asyncio
async def test_model_cache_reuses_loaded_instance(fake_whisper, tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"\x00")
    fake_whisper.transcribe.return_value = (
        iter([]),
        SimpleNamespace(duration=0.0, language="en"),
    )

    from tui_transcript.services.transcription import whisper_local
    from tui_transcript.services.transcription.whisper_local import WhisperTranscriber

    await WhisperTranscriber("small").transcribe(audio, language="en")
    await WhisperTranscriber("small").transcribe(audio, language="en")

    # Class constructor should be called only once for "small"
    import faster_whisper
    assert faster_whisper.WhisperModel.call_count == 1
    assert "small" in whisper_local._MODEL_CACHE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_whisper_transcriber.py -v`
Expected: FAIL — `whisper_local` module does not exist.

- [ ] **Step 3: Create the transcriber**

Create `src/tui_transcript/services/transcription/whisper_local.py`:

```python
"""Local Whisper transcriber via faster-whisper."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from tui_transcript.models import TranscriptParagraph, TranscriptResult
from tui_transcript.services.transcription.base import TranscriberError

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".opus", ".wma"}

# Paragraph aggregation tuning:
PARAGRAPH_GAP_SECONDS = 1.5
PARAGRAPH_MAX_SEGMENTS = 8

# Module-level cache so reloads don't happen per job.
_MODEL_CACHE: dict[str, object] = {}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def _extract_audio(video_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _load_model(name: str):
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriberError(
            "faster-whisper is not installed. Run: uv sync"
        ) from exc
    model = WhisperModel(name, device="auto", compute_type="auto")
    _MODEL_CACHE[name] = model
    return model


def _aggregate(segments) -> list[TranscriptParagraph]:
    """Group segments into paragraphs by silence gap or max-count."""
    paragraphs: list[TranscriptParagraph] = []
    current: list = []

    def flush() -> None:
        if not current:
            return
        paragraphs.append(
            TranscriptParagraph(
                start=current[0].start,
                end=current[-1].end,
                text=" ".join(s.text.strip() for s in current),
            )
        )
        current.clear()

    for seg in segments:
        if current:
            gap = seg.start - current[-1].end
            if gap >= PARAGRAPH_GAP_SECONDS or len(current) >= PARAGRAPH_MAX_SEGMENTS:
                flush()
        current.append(seg)
    flush()
    return paragraphs


class WhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def transcribe(
        self,
        file_path: Path,
        *,
        language: str = "es",
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptResult:
        def _notify(msg: str) -> None:
            if on_status:
                on_status(msg)

        tmp_dir: str | None = None
        try:
            if not _is_audio_file(file_path):
                if not _has_ffmpeg():
                    raise TranscriberError(
                        "ffmpeg not found — required to extract audio for local Whisper."
                    )
                _notify("Extracting audio track (ffmpeg)...")
                tmp_dir = tempfile.mkdtemp(prefix="tui_transcript_whisper_")
                wav_path = Path(tmp_dir) / "audio.wav"
                await asyncio.to_thread(_extract_audio, file_path, wav_path)
                source_path = wav_path
            else:
                source_path = file_path

            _notify(f"Loading Whisper model '{self._model_name}'...")
            model = await asyncio.to_thread(_load_model, self._model_name)

            whisper_lang = None if language == "multi" else language
            _notify("Running local Whisper transcription...")

            def _run():
                return model.transcribe(
                    str(source_path),
                    language=whisper_lang,
                    vad_filter=True,
                    beam_size=5,
                )

            segments_iter, info = await asyncio.to_thread(_run)

            collected = []
            duration = getattr(info, "duration", 0.0) or 0.0
            for seg in segments_iter:
                collected.append(seg)
                if duration > 0:
                    pct = min(100, int((seg.end / duration) * 100))
                    _notify(f"  {seg.end:.0f}s/{duration:.0f}s ({pct}%)")

            paragraphs = _aggregate(collected)
            full_text = " ".join(p.text for p in paragraphs).strip()
            return TranscriptResult(text=full_text, paragraphs=paragraphs)
        finally:
            if tmp_dir is not None:
                await asyncio.to_thread(shutil.rmtree, tmp_dir, True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_whisper_transcriber.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/transcription/whisper_local.py tests/test_whisper_transcriber.py
git commit -m "Add local Whisper transcriber"
```

---

## Task 6: Add engine + whisper_model to VideoJob

**Files:**
- Modify: `src/tui_transcript/models.py`
- Test: `tests/test_video_job_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_video_job_engine.py`:

```python
from pathlib import Path
from tui_transcript.models import VideoJob


def test_video_job_default_engine_is_deepgram():
    job = VideoJob(path=Path("/tmp/x.mp4"))
    assert job.engine == "deepgram"
    assert job.whisper_model is None


def test_video_job_engine_serializes():
    job = VideoJob(
        path=Path("/tmp/x.mp4"),
        engine="whisper_local",
        whisper_model="large-v3",
    )
    d = job.to_dict()
    assert d["engine"] == "whisper_local"
    assert d["whisper_model"] == "large-v3"


def test_video_job_engine_round_trip():
    job = VideoJob(
        path=Path("/tmp/x.mp4"),
        engine="whisper_local",
        whisper_model="medium",
    )
    restored = VideoJob.from_dict(job.to_dict())
    assert restored.engine == "whisper_local"
    assert restored.whisper_model == "medium"


def test_video_job_engine_defaults_when_missing_in_dict():
    restored = VideoJob.from_dict({"path": "/tmp/x.mp4"})
    assert restored.engine == "deepgram"
    assert restored.whisper_model is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_job_engine.py -v`
Expected: FAIL — `engine` attribute does not exist.

- [ ] **Step 3: Modify `VideoJob` in `src/tui_transcript/models.py`**

Edit `src/tui_transcript/models.py`. Update the `VideoJob` dataclass (around line 107-152):

Add after `key_moments: list[KeyMoment] = field(default_factory=list)`:

```python
    engine: str = "deepgram"
    whisper_model: str | None = None
```

Update `to_dict` to include the two new fields:

```python
    def to_dict(self) -> dict:
        """Serialize for API/JSON. Path becomes string."""
        return {
            "path": str(self.path),
            "language": self.language,
            "status": self.status.value,
            "progress": self.progress,
            "transcript": self.transcript,
            "output_path": self.output_path,
            "error": self.error,
            "key_moments": [
                {"timestamp": m.timestamp, "description": m.description}
                for m in self.key_moments
            ],
            "engine": self.engine,
            "whisper_model": self.whisper_model,
        }
```

Update `from_dict` to read them:

```python
    @classmethod
    def from_dict(cls, data: dict) -> VideoJob:
        path = data["path"]
        if not isinstance(path, Path):
            path = Path(path)
        return cls(
            path=path,
            language=data.get("language", "es"),
            status=JobStatus(data.get("status", JobStatus.PENDING.value)),
            progress=data.get("progress", 0.0),
            transcript=data.get("transcript", ""),
            output_path=data.get("output_path", ""),
            error=data.get("error", ""),
            key_moments=[
                KeyMoment(**m) for m in data.get("key_moments", [])
            ],
            engine=data.get("engine", "deepgram"),
            whisper_model=data.get("whisper_model"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_job_engine.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/models.py tests/test_video_job_engine.py
git commit -m "Add engine and whisper_model to VideoJob"
```

---

## Task 7: Wire pipeline through `get_transcriber`

**Files:**
- Modify: `src/tui_transcript/services/pipeline.py:139-144`
- Modify: `tests/test_pipeline_overrides.py`

- [ ] **Step 1: Extend the existing test file with engine parametrization**

Open `tests/test_pipeline_overrides.py` and add at the end:

```python
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,model", [("deepgram", None), ("whisper_local", "small")])
async def test_pipeline_dispatches_per_engine(monkeypatch, tmp_path, engine, model):
    """The pipeline must call get_transcriber with the job's engine + model."""
    from tui_transcript.models import (
        AppConfig, JobStatus, NamingMode, TranscriptResult, VideoJob,
    )
    from tui_transcript.services import pipeline as pipeline_mod

    media = tmp_path / "clip.wav"
    media.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

    job = VideoJob(
        path=media,
        language="en",
        engine=engine,
        whisper_model=model,
    )
    config = AppConfig(
        deepgram_api_key="dg-key",
        anthropic_api_key="",
        prefix="Test",
        naming_mode=NamingMode.ORIGINAL,
    )

    captured = {}

    class FakeTranscriber:
        async def transcribe(self, path, *, language, on_status=None):
            return TranscriptResult(text="hello world", paragraphs=[])

    def fake_get_transcriber(eng, *, model, deepgram_api_key):
        captured["engine"] = eng
        captured["model"] = model
        captured["dg_key"] = deepgram_api_key
        return FakeTranscriber()

    monkeypatch.setattr(pipeline_mod, "get_transcriber", fake_get_transcriber)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    await pipeline_mod.run_pipeline(
        config, [job], output_dir=out_dir, course_name="Test"
    )

    assert captured["engine"] == engine
    assert captured["model"] == model
    assert job.status == JobStatus.DONE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_overrides.py -v -k dispatches_per_engine`
Expected: FAIL — `pipeline_mod` has no attribute `get_transcriber`.

- [ ] **Step 3: Modify `src/tui_transcript/services/pipeline.py`**

At the top of the file, add:

```python
from tui_transcript.services.transcription import get_transcriber
```

Replace the current direct `transcribe` call (lines ~139-144) with:

```python
                transcriber = get_transcriber(
                    job.engine,
                    model=job.whisper_model,
                    deepgram_api_key=config.deepgram_api_key,
                )
                transcript_result = await transcriber.transcribe(
                    job.path,
                    language=job.language,
                    on_status=_on_status,
                )
```

Remove the now-unused import: delete the line `from tui_transcript.services.transcription import transcribe` if it exists (or update it to keep only what's used).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_overrides.py -v`
Expected: all parametrized cases pass.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/services/pipeline.py tests/test_pipeline_overrides.py
git commit -m "Pipeline dispatches transcribe via engine selector"
```

---

## Task 8: API schema + validation for engine/model

**Files:**
- Modify: `src/tui_transcript/api/schemas.py`
- Modify: `src/tui_transcript/api/routes/transcription.py`
- Modify: `tests/test_transcription_directory.py`

- [ ] **Step 1: Extend the existing test file with engine validation cases**

Open `tests/test_transcription_directory.py` and add new tests at the end (use the existing fixtures/imports already in that file):

```python
def test_start_requires_whisper_model_when_engine_is_local(client, registered_dir, uploaded):
    payload = {
        "files": [{"id": uploaded, "language": "en", "engine": "whisper_local"}],
        "directory_id": registered_dir,
    }
    res = client.post("/api/transcription/start", json=payload)
    assert res.status_code == 400
    assert "whisper_model" in res.text.lower()


def test_start_requires_downloaded_model(client, registered_dir, uploaded, monkeypatch):
    from tui_transcript.services.transcription import models
    monkeypatch.setattr(models, "is_downloaded", lambda name: False)

    payload = {
        "files": [
            {
                "id": uploaded,
                "language": "en",
                "engine": "whisper_local",
                "whisper_model": "large-v3",
            }
        ],
        "directory_id": registered_dir,
    }
    res = client.post("/api/transcription/start", json=payload)
    assert res.status_code == 400
    assert "not downloaded" in res.text.lower()


def test_start_accepts_local_engine_when_model_downloaded(
    client, registered_dir, uploaded, monkeypatch
):
    from tui_transcript.services.transcription import models
    monkeypatch.setattr(models, "is_downloaded", lambda name: True)

    payload = {
        "files": [
            {
                "id": uploaded,
                "language": "en",
                "engine": "whisper_local",
                "whisper_model": "small",
            }
        ],
        "directory_id": registered_dir,
    }
    res = client.post("/api/transcription/start", json=payload)
    # We don't run the pipeline here — Deepgram key check is bypassed for local.
    assert res.status_code == 200


def test_start_unknown_engine_is_rejected(client, registered_dir, uploaded):
    payload = {
        "files": [{"id": uploaded, "language": "en", "engine": "bogus"}],
        "directory_id": registered_dir,
    }
    res = client.post("/api/transcription/start", json=payload)
    assert res.status_code == 422  # pydantic Literal validation
```

If `tests/test_transcription_directory.py` doesn't already have `client`, `registered_dir`, `uploaded` fixtures, find the existing test in that file and reuse the patterns it uses for setup.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcription_directory.py -v`
Expected: new tests fail (422/400 don't match, or schema rejects unknown fields).

- [ ] **Step 3: Update `src/tui_transcript/api/schemas.py`**

Find the `FileSpec` class (around line 46-50) and replace with:

```python
from typing import Literal


class FileSpec(BaseModel):
    """File + language + engine for transcription start."""

    id: str
    language: str = "es"
    engine: Literal["deepgram", "whisper_local"] = "deepgram"
    whisper_model: Literal["small", "medium", "large-v3"] | None = None
```

- [ ] **Step 4: Update `src/tui_transcript/api/routes/transcription.py`**

In `start_transcription` (around line 74-126), replace the body. Specifically:

a) Move the Deepgram key check so it only fails when at least one job uses Deepgram.
b) Add a `whisper_model` required + downloaded check for local jobs.
c) Pass `engine` and `whisper_model` through to `VideoJob`.

Replace lines starting with `config = EnvConfigStore().load()` through the end of the for-loop building jobs:

```python
    config = EnvConfigStore().load()

    # Validate engine-specific requirements before doing any work.
    needs_deepgram = any(spec.engine == "deepgram" for spec in req.files)
    if needs_deepgram and not config.deepgram_api_key:
        raise HTTPException(400, "Deepgram API key not configured")

    from tui_transcript.services.transcription import models as local_models

    for spec in req.files:
        if spec.engine == "whisper_local":
            if not spec.whisper_model:
                raise HTTPException(
                    400, "whisper_model is required when engine='whisper_local'"
                )
            if not local_models.is_downloaded(spec.whisper_model):
                raise HTTPException(
                    400,
                    f"Model '{spec.whisper_model}' is not downloaded. "
                    "Download it in Settings.",
                )

    from tui_transcript.services.history import HistoryDB

    db = HistoryDB()
    try:
        directory = db.get_directory(req.directory_id)
    finally:
        db.close()

    if directory is None:
        raise HTTPException(404, f"Directory id {req.directory_id} not found")

    dir_path = Path(directory["path"])
    if not dir_path.is_dir():
        raise HTTPException(
            422,
            f"Class folder missing at {directory['path']}. Please re-attach in Documents.",
        )

    jobs: list[VideoJob] = []
    for spec in req.files:
        upload = get_upload(spec.id)
        if not upload:
            raise HTTPException(404, f"File not found: {spec.id}")
        job = VideoJob(
            path=upload["path"],
            language=spec.language,
            status=JobStatus.PENDING,
            engine=spec.engine,
            whisper_model=spec.whisper_model,
        )
        jobs.append(job)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcription_directory.py -v`
Expected: all pass (existing + new).

Run: `uv run pytest -q`
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/api/schemas.py src/tui_transcript/api/routes/transcription.py tests/test_transcription_directory.py
git commit -m "Validate engine + model on /transcription/start"
```

---

## Task 9: Local models API routes

**Files:**
- Create: `src/tui_transcript/api/routes/models.py`
- Modify: `src/tui_transcript/api/main.py`
- Test: `tests/test_models_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_api.py`:

```python
"""Tests for the /api/models/local routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tui_transcript.api.main import app


def test_list_local_models(monkeypatch):
    fake = [
        {"name": "small", "repo_id": "x/small", "size_mb": 466, "downloaded": True},
        {"name": "medium", "repo_id": "x/medium", "size_mb": 1530, "downloaded": False},
    ]
    from tui_transcript.services.transcription import models as m
    monkeypatch.setattr(m, "list_models", lambda: fake)

    with TestClient(app) as client:
        res = client.get("/api/models/local")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["name"] == "small"
    assert body[0]["downloaded"] is True


def test_download_unknown_model_returns_404(monkeypatch):
    with TestClient(app) as client:
        res = client.post("/api/models/local/bogus/download")
    assert res.status_code == 404


def test_download_emits_progress_then_done(monkeypatch):
    from tui_transcript.services.transcription import models as m

    async def fake_download(name, on_progress=None):
        if on_progress:
            on_progress(0)
            on_progress(100)

    monkeypatch.setattr(m, "download", fake_download)

    with TestClient(app) as client:
        with client.stream("POST", "/api/models/local/small/download") as res:
            assert res.status_code == 200
            body = b"".join(res.iter_bytes()).decode()
    assert '"progress": 0' in body
    assert '"progress": 100' in body
    assert '"done"' in body


def test_delete_local_model(monkeypatch):
    called = {}

    async def fake_remove(name):
        called["name"] = name

    from tui_transcript.services.transcription import models as m
    monkeypatch.setattr(m, "remove", fake_remove)

    with TestClient(app) as client:
        res = client.delete("/api/models/local/small")
    assert res.status_code == 204
    assert called == {"name": "small"}


def test_delete_unknown_model_returns_404():
    with TestClient(app) as client:
        res = client.delete("/api/models/local/bogus")
    assert res.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_api.py -v`
Expected: FAIL — `/api/models/local` endpoints don't exist (404 on every call).

- [ ] **Step 3: Create the routes module**

Create `src/tui_transcript/api/routes/models.py`:

```python
"""Routes for local Whisper model management."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tui_transcript.services.transcription import models as local_models

router = APIRouter(prefix="/models/local", tags=["models"])


@router.get("")
def list_local_models() -> list[dict]:
    return local_models.list_models()


def _sse(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


@router.post("/{name}/download")
async def download_local_model(name: str) -> StreamingResponse:
    if name not in local_models.LOCAL_MODELS:
        raise HTTPException(404, f"Unknown model: {name}")

    queue: asyncio.Queue = asyncio.Queue()

    async def runner() -> None:
        try:
            def on_progress(pct: int) -> None:
                queue.put_nowait({"type": "progress", "progress": pct})

            await local_models.download(name, on_progress=on_progress)
            queue.put_nowait({"type": "done"})
        except Exception as exc:
            queue.put_nowait({"type": "error", "message": str(exc)})
        finally:
            queue.put_nowait(None)  # sentinel

    asyncio.create_task(runner())

    async def stream():
        while True:
            event = await queue.get()
            if event is None:
                return
            yield _sse(event)
            if event.get("type") in {"done", "error"}:
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{name}", status_code=204)
async def delete_local_model(name: str) -> None:
    if name not in local_models.LOCAL_MODELS:
        raise HTTPException(404, f"Unknown model: {name}")
    await local_models.remove(name)
```

- [ ] **Step 4: Register the router in `src/tui_transcript/api/main.py`**

Edit the import block (around line 15) to include `models`:

```python
from tui_transcript.api.routes import (
    collections,
    config,
    documents,
    files,
    models,
    paths,
    search,
    tags,
    transcription,
)
```

Then in the router-include block (around line 76), add:

```python
app.include_router(models.router, prefix="/api")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_models_api.py -v`
Expected: 5 passed.

Run: `uv run pytest -q`
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/api/routes/models.py src/tui_transcript/api/main.py tests/test_models_api.py
git commit -m "Add /api/models/local list/download/delete routes"
```

---

## Task 10: Frontend API client — engine fields + model endpoints

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update `FileSpec` interface and `startTranscription`**

In `frontend/src/api/client.ts`, replace the `FileSpec` interface (around line 23):

```ts
export type Engine = 'deepgram' | 'whisper_local';
export type WhisperModelName = 'small' | 'medium' | 'large-v3';

export interface FileSpec {
  id: string;
  language: string;
  engine?: Engine;
  whisper_model?: WhisperModelName;
}
```

The existing `startTranscription(fileSpecs, directoryId)` already serializes `fileSpecs` directly — no change needed to the call.

- [ ] **Step 2: Add local-model API helpers**

Append to `frontend/src/api/client.ts` (above the existing SSE block):

```ts
// ------------------------------------------------------------------
// Local Whisper models
// ------------------------------------------------------------------

export interface LocalModelInfo {
  name: WhisperModelName;
  repo_id: string;
  size_mb: number;
  downloaded: boolean;
}

export async function listLocalModels(): Promise<LocalModelInfo[]> {
  const res = await fetch(`${API_BASE}/models/local`);
  if (!res.ok) throw new Error('Failed to list local models');
  return res.json();
}

export async function deleteLocalModel(name: WhisperModelName): Promise<void> {
  const res = await fetch(`${API_BASE}/models/local/${name}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete model');
  }
}

export type ModelDownloadEvent =
  | { type: 'progress'; progress: number }
  | { type: 'done' }
  | { type: 'error'; message: string };

export function subscribeToModelDownload(
  name: WhisperModelName,
  onEvent: (event: ModelDownloadEvent) => void,
  onError?: (err: Error) => void
): () => void {
  let cancelled = false;
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/models/local/${name}/download`, {
        method: 'POST',
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Download failed');
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!cancelled) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // Split by SSE event delimiter
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';
        for (const block of events) {
          const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(5).trim());
            onEvent(payload);
          } catch {
            // skip parse errors
          }
        }
      }
    } catch (e) {
      if (!cancelled) onError?.(e as Error);
    }
  })();

  return () => {
    cancelled = true;
    controller.abort();
  };
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "Add engine fields and local-model API client helpers"
```

---

## Task 11: `EngineSelect` component + Dashboard wiring

**Files:**
- Create: `frontend/src/components/EngineSelect.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/EngineSelect.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  listLocalModels,
  type Engine,
  type LocalModelInfo,
  type WhisperModelName,
} from '@/api/client';

export interface EngineSelectProps {
  engine: Engine;
  whisperModel: WhisperModelName | undefined;
  onEngineChange: (engine: Engine) => void;
  onWhisperModelChange: (model: WhisperModelName | undefined) => void;
  disabled?: boolean;
}

export function EngineSelect({
  engine,
  whisperModel,
  onEngineChange,
  onWhisperModelChange,
  disabled,
}: EngineSelectProps) {
  const { data: localModels = [] } = useQuery<LocalModelInfo[]>({
    queryKey: ['local-models'],
    queryFn: listLocalModels,
    enabled: engine === 'whisper_local',
  });
  const downloaded = localModels.filter((m) => m.downloaded);

  return (
    <div className="flex items-center gap-2">
      <Select
        value={engine}
        onValueChange={(v) => {
          onEngineChange(v as Engine);
          if (v === 'deepgram') onWhisperModelChange(undefined);
        }}
        disabled={disabled}
      >
        <SelectTrigger className="w-[140px] h-8">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="deepgram">Deepgram</SelectItem>
          <SelectItem value="whisper_local">Local Whisper</SelectItem>
        </SelectContent>
      </Select>

      {engine === 'whisper_local' && (
        <Select
          value={whisperModel ?? ''}
          onValueChange={(v) => onWhisperModelChange(v as WhisperModelName)}
          disabled={disabled || downloaded.length === 0}
        >
          <SelectTrigger className="w-[120px] h-8">
            <SelectValue
              placeholder={
                downloaded.length === 0 ? 'No models' : 'Pick model'
              }
            />
          </SelectTrigger>
          <SelectContent>
            {downloaded.map((m) => (
              <SelectItem key={m.name} value={m.name}>
                {m.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire `EngineSelect` into `Dashboard.tsx`**

In `frontend/src/pages/Dashboard.tsx`:

a) Update the imports near the top:

```tsx
import {
  getConfig,
  uploadFiles,
  startTranscription,
  subscribeToProgress,
  getTranscriptionStatus,
  openPath,
  getDirectories,
  type UploadedFile,
  type FileSpec,
  type SSEEvent,
  type JobStatus,
  type KeyMoment,
  type DirectoryEntry,
  type Engine,
  type WhisperModelName,
} from '@/api/client';
import { EngineSelect } from '@/components/EngineSelect';
```

b) Update the `FileWithLang` type definition:

```tsx
type FileWithLang = UploadedFile & {
  language: string;
  engine: Engine;
  whisperModel?: WhisperModelName;
};
```

c) Update the file-upload code (`handleFiles`) so newly added files default to deepgram:

Find the line in `handleFiles`:
```tsx
...uploaded.map((u) => ({ ...u, language: 'es' })),
```
Replace with:
```tsx
...uploaded.map((u) => ({ ...u, language: 'es', engine: 'deepgram' as Engine, whisperModel: undefined })),
```

d) Add helpers near `setFileLanguage` (around line 114):

```tsx
const setFileEngine = (id: string, engine: Engine) => {
  setFiles((prev) =>
    prev.map((f) =>
      f.id === id
        ? { ...f, engine, whisperModel: engine === 'deepgram' ? undefined : f.whisperModel }
        : f
    )
  );
};

const setFileWhisperModel = (id: string, model: WhisperModelName | undefined) => {
  setFiles((prev) =>
    prev.map((f) => (f.id === id ? { ...f, whisperModel: model } : f))
  );
};
```

e) Update the `start` function to skip the Deepgram-key alert when no file uses Deepgram, and pass engine/model fields through:

Replace the block from `if (!config?.deepgram_api_key …)` through the call to `startTranscription`:

```tsx
const needsDeepgram = files.some((f) => f.engine === 'deepgram');
if (needsDeepgram && (!config?.deepgram_api_key || config.deepgram_api_key === '***')) {
  alert('Configure your Deepgram API key in Settings first.');
  return;
}
const localMissingModel = files.find(
  (f) => f.engine === 'whisper_local' && !f.whisperModel
);
if (localMissingModel) {
  alert(`Pick a Whisper model for ${localMissingModel.name}.`);
  return;
}
if (directoryId == null) {
  alert('Select a class first.');
  return;
}
const dir = directories.find((d) => d.id === directoryId);
if (!dir || !dir.exists) {
  alert('Selected class folder is missing — re-attach it in Documents.');
  return;
}
setProcessing(true);
setLogs([]);
setJobs({});
setStatusLabel('Starting...');
try {
  const specs: FileSpec[] = files.map((f) => ({
    id: f.id,
    language: f.language,
    engine: f.engine,
    whisper_model: f.whisperModel,
  }));
  const { session_id } = await startTranscription(specs, directoryId);
```

(Leave the rest of the `subscribeToProgress` block unchanged.)

f) Render `EngineSelect` inside the per-file row, right after the Language `Select` (around line 309):

```tsx
<EngineSelect
  engine={f.engine}
  whisperModel={f.whisperModel}
  onEngineChange={(e) => setFileEngine(f.id, e)}
  onWhisperModelChange={(m) => setFileWhisperModel(f.id, m)}
  disabled={processing}
/>
```

- [ ] **Step 3: Type-check + start the dev servers manually to smoke-test**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: 0 errors.

(Skip a runtime check here — see Task 13.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/EngineSelect.tsx frontend/src/pages/Dashboard.tsx
git commit -m "Add per-job engine + Whisper model selector"
```

---

## Task 12: `LocalModelsPanel` + Settings wiring

**Files:**
- Create: `frontend/src/components/LocalModelsPanel.tsx`
- Modify: `frontend/src/pages/Config.tsx`

- [ ] **Step 1: Create the panel component**

Create `frontend/src/components/LocalModelsPanel.tsx`:

```tsx
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Loader2, Trash2, Download, Check } from 'lucide-react';
import {
  listLocalModels,
  deleteLocalModel,
  subscribeToModelDownload,
  type LocalModelInfo,
  type WhisperModelName,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function LocalModelsPanel() {
  const queryClient = useQueryClient();
  const { data: models = [], isLoading } = useQuery<LocalModelInfo[]>({
    queryKey: ['local-models'],
    queryFn: listLocalModels,
  });
  const [progress, setProgress] = useState<Record<string, number>>({});

  const formatSize = (mb: number) =>
    mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;

  const startDownload = (name: WhisperModelName) => {
    setProgress((p) => ({ ...p, [name]: 0 }));
    subscribeToModelDownload(
      name,
      (event) => {
        if (event.type === 'progress') {
          setProgress((p) => ({ ...p, [name]: event.progress }));
        } else if (event.type === 'done') {
          setProgress((p) => {
            const next = { ...p };
            delete next[name];
            return next;
          });
          queryClient.invalidateQueries({ queryKey: ['local-models'] });
        } else if (event.type === 'error') {
          alert(`Download failed: ${event.message}`);
          setProgress((p) => {
            const next = { ...p };
            delete next[name];
            return next;
          });
        }
      },
      (err) => {
        alert(err.message);
        setProgress((p) => {
          const next = { ...p };
          delete next[name];
          return next;
        });
      }
    );
  };

  const remove = async (name: WhisperModelName) => {
    if (!confirm(`Remove ${name} model from local cache?`)) return;
    try {
      await deleteLocalModel(name);
      queryClient.invalidateQueries({ queryKey: ['local-models'] });
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Local Whisper models</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {models.map((m) => {
          const inflight = progress[m.name];
          return (
            <div
              key={m.name}
              className="flex items-center gap-3 rounded-md border bg-card p-3 text-sm"
            >
              <span className="flex-1 font-medium">{m.name}</span>
              <span className="text-muted-foreground shrink-0">
                {formatSize(m.size_mb)}
              </span>
              {m.downloaded ? (
                <>
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <Check className="size-3.5" /> Downloaded
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(m.name)}
                    title="Remove model"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </>
              ) : inflight !== undefined ? (
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  Downloading {inflight}%
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startDownload(m.name)}
                >
                  <Download className="size-4 mr-1.5" />
                  Download
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Wire the panel into `Config.tsx`**

Open `frontend/src/pages/Config.tsx`. Add the import near the top:

```tsx
import { LocalModelsPanel } from '@/components/LocalModelsPanel';
```

Render `<LocalModelsPanel />` as a sibling near the bottom of the existing settings layout (after the last existing `Card`), inside whatever wrapper is used (e.g. `<div className="space-y-6">`):

```tsx
<LocalModelsPanel />
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LocalModelsPanel.tsx frontend/src/pages/Config.tsx
git commit -m "Add Local Whisper models panel to Settings"
```

---

## Task 13: End-to-end smoke test (manual)

**Files:** none — manual verification step.

- [ ] **Step 1: Start the backend**

Run (in terminal A): `uv run tui-transcript-api`
Expected: uvicorn starts on `:8000`, no startup errors.

- [ ] **Step 2: Start the frontend**

Run (in terminal B): `cd frontend && npm run dev`
Expected: Vite starts on `:5173`.

- [ ] **Step 3: Verify Settings panel**

In a browser, open `http://localhost:5173`, navigate to Settings.
Expected:
- "Local Whisper models" card appears at the bottom.
- Three rows: small / medium / large-v3, each with a Download button.

- [ ] **Step 4: Download `small`**

Click Download next to `small`.
Expected: spinner with "Downloading …%". On completion: green checkmark + Trash button.

This is a real download (~500 MB) and may take several minutes on first run.

- [ ] **Step 5: Verify Transcribe view shows engine selector**

Go to Transcribe. Drop in a short audio file (.mp3 or .wav).
Expected: each file row shows Language + Engine (Deepgram default) selectors.

- [ ] **Step 6: Run a job with `whisper_local` + `small`**

Switch the engine to `Local Whisper`, pick `small`. Pick a class. Click Start.
Expected:
- Status messages mention "Loading Whisper model" and "Running local Whisper transcription".
- Job reaches DONE; output Markdown file appears in the class directory.
- No Deepgram API call occurs (network tab confirms).

- [ ] **Step 7: Verify Deepgram path still works**

Add another file, leave engine on Deepgram, run.
Expected: existing Deepgram path runs unchanged. Transcript saved.

- [ ] **Step 8: Run the full backend suite once more**

Run: `uv run pytest -q`
Expected: green.

- [ ] **Step 9: Commit nothing** (manual step)

If any code adjustments were needed, commit with a clear message describing the fix. Otherwise this task is complete.

---

## Task 14: Open PR

**Files:** none.

- [ ] **Step 1: Push branch**

Run: `git push -u origin feature/local-whisper-impl`
Expected: branch published.

- [ ] **Step 2: Open PR via gh CLI**

```bash
gh pr create --title "Add local Whisper transcription engine" --body "$(cat <<'EOF'
## Summary
- Adds `WhisperTranscriber` (faster-whisper) alongside `DeepgramTranscriber` behind a shared `Transcriber` Protocol.
- Per-job engine + model selector in the Transcribe view.
- New Settings panel to download/remove local models.

## Test plan
- [ ] `uv run pytest -q` green
- [ ] Manual: download `small` from Settings, run a transcription with engine=Local
- [ ] Manual: confirm Deepgram path still works on the same screen

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Goals (eliminate hard Deepgram dep, per-job choice, unchanged downstream, cross-platform install) → Tasks 1, 7, 8, 11.
- Non-goals (no diarization, no global default, serial processing) → enforced by what is *not* in the plan.
- UX: Transcribe per-row selector → Task 11. Settings models panel → Task 12.
- Architecture: package layout + Protocol + selector → Tasks 2, 3, 5, 7.
- Whisper internals: ffmpeg reuse, model cache, language mapping, paragraph aggregation → Task 5.
- Local model registry (list/is_downloaded/download/remove) → Task 4.
- API: `engine` + `whisper_model` on `FileSpec`, validation, `VideoJob` fields, model routes → Tasks 6, 8, 9.
- Pipeline change → Task 7.
- Frontend: client.ts, EngineSelect, LocalModelsPanel → Tasks 10, 11, 12.
- Dependencies → Task 1.
- Error handling: missing model 400, missing key only when needed, import error message → Task 8 + Task 5 (TranscriberError on missing faster-whisper).
- Testing: whisper_transcriber, models_api, transcription_directory extension, pipeline_overrides extension → Tasks 4, 5, 7, 8, 9.

**Placeholder scan:** No TBDs, no "implement later", no "similar to Task N", no skipped code blocks.

**Type consistency:**
- `Transcriber.transcribe(file_path, *, language, on_status)` — same shape used by both `DeepgramTranscriber` and `WhisperTranscriber`, and matched by the `_FakeTranscriber` test fixture in Task 7.
- `get_transcriber(engine, *, model, deepgram_api_key)` — same signature in Task 2 (`__init__.py`) and Task 7 (pipeline call).
- `FileSpec` — Python schema matches TypeScript `FileSpec` interface (`engine`, `whisper_model` / `whisperModel` mapping handled inside `Dashboard.tsx`).
- Model names — `Literal["small", "medium", "large-v3"]` matches `LOCAL_MODELS` keys and TS `WhisperModelName`.
- `local_models.list_models()` returns `[{"name", "repo_id", "size_mb", "downloaded"}]` — matches `LocalModelInfo` TS interface.
