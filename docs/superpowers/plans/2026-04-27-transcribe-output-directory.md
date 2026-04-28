# Per-Class Output Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move output directory and course name out of global Settings into a per-batch class selector on the Transcribe view, with inline create using the same form pattern as the Documents page.

**Architecture:** Frontend dropdown sourced from existing `/documents/directories` endpoint with inline-create using the existing `POST /documents/directories` endpoint. Pipeline accepts optional `output_dir` and `course_name` overrides; API enforces directory_id presence at the transcription route. Settings UI loses the two fields; env-backed `EnvConfigStore` keeps them so the TUI is unaffected.

**Tech Stack:** FastAPI / Pydantic v2 / SQLite (HistoryDB), React 19 / Vite / @tanstack/react-query, pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-04-27-transcribe-output-directory-design.md`

---

## File Map

**Modified (backend):**
- `src/tui_transcript/api/schemas.py` — drop fields from `ConfigResponse`/`ConfigUpdate`; add `directory_id` to `TranscriptionStartRequest`
- `src/tui_transcript/api/routes/config.py` — drop fields from get/put handlers
- `src/tui_transcript/api/routes/transcription.py` — look up directory, pass overrides to pipeline
- `src/tui_transcript/services/pipeline.py` — accept optional `output_dir` and `course_name` overrides
- `src/tui_transcript/api/main.py` — startup hook: auto-register `MARKDOWN_OUTPUT_DIR` if no directories exist

**Modified (frontend):**
- `frontend/src/api/client.ts` — drop fields from `Config`/`ConfigUpdate`; add `directoryId` to `startTranscription`
- `frontend/src/pages/Documents.tsx` — extract add-directory form into shared component
- `frontend/src/pages/Dashboard.tsx` — add Class card above drop zone
- `frontend/src/pages/Config.tsx` — remove output-directory and course-name fields

**Created:**
- `frontend/src/components/DirectoryForm.tsx` — shared form (Name + Path + Browse) used by Documents and Dashboard
- `tests/test_transcription_directory.py` — backend tests for directory_id flow
- `tests/test_config_api.py` — backend tests confirming the dropped fields

---

## Task 1: Pipeline accepts output_dir and course_name overrides

**Files:**
- Modify: `src/tui_transcript/services/pipeline.py`
- Test: `tests/test_pipeline_overrides.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_overrides.py`:

```python
"""Verify run_pipeline honors output_dir and course_name overrides."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tui_transcript.models import (
    AppConfig,
    JobStatus,
    NamingMode,
    TranscriptResult,
    VideoJob,
)
from tui_transcript.services.pipeline import run_pipeline


_orig_history_init = None


@pytest.fixture()
def _isolated_history(tmp_path):
    """Force HistoryDB to a temp file so tests don't pollute the real DB."""
    from tui_transcript.services.history import HistoryDB

    global _orig_history_init
    if _orig_history_init is None:
        _orig_history_init = HistoryDB.__init__

    db_file = tmp_path / "history.db"

    def patched(self, p=db_file):
        _orig_history_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_file


def _fake_video(tmp_path: Path) -> Path:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake")
    return p


def test_pipeline_writes_to_override_dir_with_override_course_name(
    tmp_path, _isolated_history
):
    chosen_dir = tmp_path / "class_alpha"
    chosen_dir.mkdir()
    config = AppConfig(
        deepgram_api_key="dg-test",
        naming_mode=NamingMode.SEQUENTIAL,
        prefix="Lec",
        markdown_output_dir=str(tmp_path / "wrong"),
        course_name="WRONG_COURSE",
    )
    job = VideoJob(path=_fake_video(tmp_path), language="en")

    fake_transcript = TranscriptResult(text="hello world", paragraphs=[])

    with patch(
        "tui_transcript.services.pipeline.transcribe",
        new=AsyncMock(return_value=fake_transcript),
    ), patch(
        "tui_transcript.services.pipeline.get_media_duration_seconds",
        return_value=120.0,
    ):
        asyncio.run(
            run_pipeline(
                config,
                [job],
                output_dir=chosen_dir,
                course_name="Algorithms 101",
            )
        )

    assert job.status == JobStatus.DONE
    assert job.output_path
    out = Path(job.output_path)
    assert out.parent == chosen_dir, f"Output landed in {out.parent}, not {chosen_dir}"
    body = out.read_text()
    assert "course_name: Algorithms 101" in body
    assert "WRONG_COURSE" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline_overrides.py -v`
Expected: FAIL — `run_pipeline()` does not accept `output_dir` or `course_name` keyword arguments.

- [ ] **Step 3: Update `run_pipeline` signature and use overrides**

In `src/tui_transcript/services/pipeline.py`, change the `run_pipeline` signature and use the overrides for the exporter and frontmatter. Replace the function definition (currently starts at line 68) and the exporter setup:

Old (lines 68–86 region):
```python
async def run_pipeline(
    config: AppConfig,
    jobs: list[VideoJob],
    callbacks: PipelineCallbacks | None = None,
) -> None:
    """Run the transcription + export pipeline for pending jobs.

    Mutates jobs in place. Callbacks are invoked for progress, logs, and status.
    """
    cb = callbacks or DefaultPipelineCallbacks()
    pending = [j for j in jobs if j.status == JobStatus.PENDING]
    if not pending:
        return

    from tui_transcript.services.markdown_export import MarkdownExporter
    exporter = MarkdownExporter(config.markdown_output_dir)
```

New:
```python
async def run_pipeline(
    config: AppConfig,
    jobs: list[VideoJob],
    callbacks: PipelineCallbacks | None = None,
    output_dir: Path | None = None,
    course_name: str | None = None,
) -> None:
    """Run the transcription + export pipeline for pending jobs.

    Mutates jobs in place. Callbacks are invoked for progress, logs, and status.

    When ``output_dir`` is provided, transcripts are written there instead of
    ``config.markdown_output_dir``. When ``course_name`` is provided it overrides
    ``config.course_name`` for the markdown frontmatter.
    """
    cb = callbacks or DefaultPipelineCallbacks()
    pending = [j for j in jobs if j.status == JobStatus.PENDING]
    if not pending:
        return

    from tui_transcript.services.markdown_export import MarkdownExporter
    effective_output_dir = str(output_dir) if output_dir is not None else config.markdown_output_dir
    effective_course_name = course_name if course_name is not None else config.course_name
    exporter = MarkdownExporter(effective_output_dir)
```

Then in the export call (currently around line 189), replace `course_name=config.course_name` with `course_name=effective_course_name`. And in the `doc_store.ensure_registered` call (line 220), replace `config.markdown_output_dir` with `effective_output_dir`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline_overrides.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to confirm nothing else broke**

Run: `.venv/bin/pytest tests/ -v`
Expected: All pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/services/pipeline.py tests/test_pipeline_overrides.py
git commit -m "$(cat <<'EOF'
Allow run_pipeline output_dir and course_name overrides

Lets API callers route a batch to a chosen registered directory and use
the directory's name as the markdown course_name without touching the
global env config.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TranscriptionStartRequest gains directory_id

**Files:**
- Modify: `src/tui_transcript/api/schemas.py:51-54`
- Test: `tests/test_transcription_directory.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_transcription_directory.py`:

```python
"""Verify the transcription start endpoint requires and uses directory_id."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
from tui_transcript.models import TranscriptResult
from tui_transcript.services.history import HistoryDB

_orig_init = HistoryDB.__init__


@pytest.fixture()
def _tmp_db(tmp_path):
    db_path = tmp_path / "api.db"

    def patched(self, p=db_path):
        _orig_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_path


@pytest.fixture()
def client(_tmp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    return TestClient(app)


def _register_dir(client: TestClient, tmp_path: Path) -> int:
    target = tmp_path / "Algorithms"
    target.mkdir()
    res = client.post(
        "/api/documents/directories",
        json={"name": "Algorithms", "path": str(target)},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _upload_file(client: TestClient, tmp_path: Path) -> str:
    f = tmp_path / "v.mp4"
    f.write_bytes(b"fake")
    with open(f, "rb") as fh:
        res = client.post(
            "/api/files/upload",
            files=[("files", ("v.mp4", fh, "video/mp4"))],
        )
    assert res.status_code == 200, res.text
    return res.json()["files"][0]["id"]


def test_start_requires_directory_id(client, tmp_path):
    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={"files": [{"id": file_id, "language": "en"}]},
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert any("directory_id" in str(err) for err in body.get("detail", []))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcription_directory.py::test_start_requires_directory_id -v`
Expected: FAIL — request currently succeeds because `directory_id` is not required.

- [ ] **Step 3: Add `directory_id` to schema**

In `src/tui_transcript/api/schemas.py`, replace the `TranscriptionStartRequest` class (lines 51-54):

Old:
```python
class TranscriptionStartRequest(BaseModel):
    """Request to start transcription."""

    files: list[FileSpec] = Field(..., min_length=1)
```

New:
```python
class TranscriptionStartRequest(BaseModel):
    """Request to start transcription."""

    files: list[FileSpec] = Field(..., min_length=1)
    directory_id: int = Field(..., description="ID of the registered output directory (a 'class')")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_transcription_directory.py::test_start_requires_directory_id -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/api/schemas.py tests/test_transcription_directory.py
git commit -m "$(cat <<'EOF'
Require directory_id on TranscriptionStartRequest

Pins each transcription batch to a registered output directory. The
route handler will resolve the directory and forward path + name to the
pipeline in the next change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Transcription route resolves directory and passes overrides

**Files:**
- Modify: `src/tui_transcript/api/routes/transcription.py`
- Test: `tests/test_transcription_directory.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_transcription_directory.py`:

```python
def test_start_unknown_directory_id_returns_404(client, tmp_path):
    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={
            "files": [{"id": file_id, "language": "en"}],
            "directory_id": 9999,
        },
    )
    assert res.status_code == 404, res.text


def test_start_directory_path_missing_returns_422(client, tmp_path):
    target = tmp_path / "GoneClass"
    target.mkdir()
    reg = client.post(
        "/api/documents/directories",
        json={"name": "GoneClass", "path": str(target)},
    )
    dir_id = reg.json()["id"]
    target.rmdir()

    file_id = _upload_file(client, tmp_path)
    res = client.post(
        "/api/transcription/start",
        json={
            "files": [{"id": file_id, "language": "en"}],
            "directory_id": dir_id,
        },
    )
    assert res.status_code == 422, res.text
    assert "re-attach" in res.text.lower()


def test_start_passes_dir_and_name_to_pipeline(client, tmp_path):
    dir_id = _register_dir(client, tmp_path)
    file_id = _upload_file(client, tmp_path)

    captured = {}

    async def fake_run_pipeline(config, jobs, callbacks=None, output_dir=None, course_name=None):
        captured["output_dir"] = output_dir
        captured["course_name"] = course_name

    with patch(
        "tui_transcript.api.routes.transcription.run_pipeline",
        new=fake_run_pipeline,
    ):
        res = client.post(
            "/api/transcription/start",
            json={
                "files": [{"id": file_id, "language": "en"}],
                "directory_id": dir_id,
            },
        )
        assert res.status_code == 200, res.text

        # Drain the SSE so the background task runs
        sid = res.json()["session_id"]
        with client.stream("GET", f"/api/transcription/progress/{sid}") as s:
            for line in s.iter_lines():
                if "done" in (line or ""):
                    break

    assert captured["output_dir"] == (tmp_path / "Algorithms")
    assert captured["course_name"] == "Algorithms"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_transcription_directory.py -v`
Expected: New three tests FAIL — directory_id isn't resolved yet.

- [ ] **Step 3: Update the route**

In `src/tui_transcript/api/routes/transcription.py`, replace the `start_transcription` function body (lines 65-92) and update the `_run_pipeline_with_sse` call to pass overrides:

Replace the entire `_run_pipeline_with_sse` function and `start_transcription` function. New version:

```python
async def _run_pipeline_with_sse(
    session_id: str,
    config,
    jobs: list[VideoJob],
    queue: asyncio.Queue,
    output_dir: Path,
    course_name: str,
) -> None:
    """Run pipeline, pushing events to queue."""

    class SSECallbacks:
        def on_log(_, msg: str, level: str = LogLevel.INFO) -> None:
            queue.put_nowait({"type": "log", "message": msg, "level": level})

        def on_job_status_changed(_, job: VideoJob) -> None:
            queue.put_nowait({"type": "job_status", "job": job.to_dict()})

        def on_progress_advance(_, steps: int = 1) -> None:
            queue.put_nowait({"type": "progress", "steps": steps})

        def on_status_label(_, label: str) -> None:
            queue.put_nowait({"type": "status_label", "label": label})

    try:
        await run_pipeline(
            config,
            jobs,
            callbacks=SSECallbacks(),
            output_dir=output_dir,
            course_name=course_name,
        )
    finally:
        queue.put_nowait({"type": "done"})
        complete_session(session_id)


@router.post("/start", response_model=TranscriptionStartResponse)
async def start_transcription(req: TranscriptionStartRequest) -> TranscriptionStartResponse:
    """Start transcription for uploaded files. Returns session_id for progress stream."""
    config = EnvConfigStore().load()
    if not config.deepgram_api_key:
        raise HTTPException(400, "Deepgram API key not configured")

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
        )
        jobs.append(job)

    queue: asyncio.Queue = asyncio.Queue()
    session_id = create_session(queue, jobs)

    task = asyncio.create_task(
        _run_pipeline_with_sse(
            session_id,
            config,
            jobs,
            queue,
            output_dir=dir_path,
            course_name=directory["name"],
        ),
    )
    set_session_task(session_id, task)

    return TranscriptionStartResponse(session_id=session_id)
```

Add the `Path` import at the top of the file:

```python
from pathlib import Path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transcription_directory.py -v`
Expected: All four tests PASS.

- [ ] **Step 5: Run full backend suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/api/routes/transcription.py tests/test_transcription_directory.py
git commit -m "$(cat <<'EOF'
Resolve directory_id and forward path+name to pipeline

Looks up the directory via HistoryDB, validates it exists on disk, and
hands the path and name to run_pipeline as overrides. Errors map to
404 (unknown id) and 422 (folder missing).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Strip course_name and markdown_output_dir from API config

**Files:**
- Modify: `src/tui_transcript/api/schemas.py:8-27`
- Modify: `src/tui_transcript/api/routes/config.py`
- Test: `tests/test_config_api.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_api.py`:

```python
"""Verify markdown_output_dir and course_name are not exposed by the config API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tui_transcript.api.main import app
from tui_transcript.services.history import HistoryDB

_orig_init = HistoryDB.__init__


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "cfg.db"

    def patched(self, p=db_path):
        _orig_init(self, p)

    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-x")
    with patch.object(HistoryDB, "__init__", patched):
        yield TestClient(app)


def test_get_config_does_not_expose_dropped_fields(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert "markdown_output_dir" not in body
    assert "course_name" not in body
    # Surviving fields stay
    assert "deepgram_api_key" in body
    assert "naming_mode" in body
    assert "prefix" in body
    assert "anthropic_api_key" in body


def test_put_config_rejects_dropped_fields(client):
    res = client.put("/api/config", json={"markdown_output_dir": "/tmp/x"})
    assert res.status_code == 422

    res = client.put("/api/config", json={"course_name": "X"})
    assert res.status_code == 422


def test_put_config_accepts_surviving_fields(client):
    res = client.put("/api/config", json={"prefix": "Lec"})
    assert res.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_api.py -v`
Expected: FAIL — fields are still exposed and accepted.

- [ ] **Step 3: Update schemas**

In `src/tui_transcript/api/schemas.py`, replace `ConfigResponse` and `ConfigUpdate` (lines 8-27):

Old:
```python
class ConfigResponse(BaseModel):
    """Config for GET. API key is masked."""

    deepgram_api_key: str = ""  # Masked as "***" when set
    naming_mode: str = "sequential"
    prefix: str = "Transcripcion"
    course_name: str = ""
    markdown_output_dir: str = "./output"
    anthropic_api_key: str = ""  # Masked as "***" when set


class ConfigUpdate(BaseModel):
    """Partial config update for PUT."""

    deepgram_api_key: str | None = None
    naming_mode: str | None = None
    prefix: str | None = None
    course_name: str | None = None
    markdown_output_dir: str | None = None
    anthropic_api_key: str | None = None
```

New:
```python
class ConfigResponse(BaseModel):
    """Config for GET. API key is masked.

    Note: markdown_output_dir and course_name are no longer surfaced —
    output destination is chosen per-batch via the directories registry.
    """

    model_config = {"extra": "forbid"}

    deepgram_api_key: str = ""  # Masked as "***" when set
    naming_mode: str = "sequential"
    prefix: str = "Transcripcion"
    anthropic_api_key: str = ""  # Masked as "***" when set


class ConfigUpdate(BaseModel):
    """Partial config update for PUT."""

    model_config = {"extra": "forbid"}

    deepgram_api_key: str | None = None
    naming_mode: str | None = None
    prefix: str | None = None
    anthropic_api_key: str | None = None
```

- [ ] **Step 4: Update routes**

In `src/tui_transcript/api/routes/config.py`, remove the dropped-field handling. Replace the entire file body after the `_mask_key` helper:

```python
@router.get("", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    """Get current config. API keys are masked."""
    config = EnvConfigStore().load()
    return ConfigResponse(
        deepgram_api_key=_mask_key(config.deepgram_api_key) if config.deepgram_api_key else "",
        naming_mode=config.naming_mode.value,
        prefix=config.prefix,
        anthropic_api_key=_mask_key(config.anthropic_api_key) if config.anthropic_api_key else "",
    )


@router.put("")
def put_config(update: ConfigUpdate) -> dict:
    """Update config. Only provided fields are changed."""
    store = EnvConfigStore()
    config = store.load()

    if update.deepgram_api_key is not None:
        config.deepgram_api_key = update.deepgram_api_key
    if update.naming_mode is not None:
        try:
            config.naming_mode = NamingMode(update.naming_mode)
        except ValueError:
            raise HTTPException(400, f"Invalid naming_mode: {update.naming_mode}")
    if update.prefix is not None:
        config.prefix = update.prefix
    if update.anthropic_api_key is not None:
        config.anthropic_api_key = update.anthropic_api_key

    store.save(config)
    return {"ok": True}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_api.py -v`
Expected: All three tests PASS.

- [ ] **Step 6: Run full backend suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript/api/schemas.py src/tui_transcript/api/routes/config.py tests/test_config_api.py
git commit -m "$(cat <<'EOF'
Drop markdown_output_dir and course_name from web config API

The values still live in AppConfig and EnvConfigStore so the TUI keeps
working, but they are no longer accepted or returned by /api/config.
The web UI now sets output destination per batch via the directory
registry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Auto-register legacy MARKDOWN_OUTPUT_DIR on startup

**Files:**
- Modify: `src/tui_transcript/api/main.py`
- Test: `tests/test_startup_migration.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_startup_migration.py`:

```python
"""Verify legacy env-based output dir is auto-registered when no directories exist."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tui_transcript.services.history import HistoryDB

_orig_init = HistoryDB.__init__


@pytest.fixture()
def _tmp_db(tmp_path):
    db_path = tmp_path / "startup.db"

    def patched(self, p=db_path):
        _orig_init(self, p)

    with patch.object(HistoryDB, "__init__", patched):
        yield db_path


def test_auto_registers_env_dir_when_empty(tmp_path, _tmp_db, monkeypatch):
    legacy = tmp_path / "legacy_output"
    legacy.mkdir()
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(legacy))
    monkeypatch.setenv("COURSE_NAME", "Old Course")

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert len(dirs) == 1
    assert dirs[0]["name"] == "Old Course"
    assert Path(dirs[0]["path"]) == legacy.resolve()


def test_skips_when_directories_already_exist(tmp_path, _tmp_db, monkeypatch):
    existing = tmp_path / "Already"
    existing.mkdir()
    db = HistoryDB()
    try:
        db.register_directory("Already", str(existing.resolve()))
    finally:
        db.close()

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(legacy))

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert len(dirs) == 1
    assert dirs[0]["name"] == "Already"


def test_skips_when_env_dir_does_not_exist(tmp_path, _tmp_db, monkeypatch):
    monkeypatch.setenv("MARKDOWN_OUTPUT_DIR", str(tmp_path / "nope"))

    from tui_transcript.api.main import auto_register_legacy_output_dir

    auto_register_legacy_output_dir()

    db = HistoryDB()
    try:
        dirs = db.list_directories()
    finally:
        db.close()
    assert dirs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_startup_migration.py -v`
Expected: FAIL — `auto_register_legacy_output_dir` doesn't exist.

- [ ] **Step 3: Add the startup hook**

In `src/tui_transcript/api/main.py`, add after the imports:

```python
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


def auto_register_legacy_output_dir() -> None:
    """If no directories are registered yet but MARKDOWN_OUTPUT_DIR is set
    and exists on disk, register it once so existing TUI users don't lose
    their setup when they open the web app.
    """
    from tui_transcript.services.history import HistoryDB

    legacy_path = os.environ.get("MARKDOWN_OUTPUT_DIR", "").strip()
    if not legacy_path:
        return
    p = Path(legacy_path).expanduser().resolve()
    if not p.is_dir():
        return

    db = HistoryDB()
    try:
        if db.list_directories():
            return
        name = os.environ.get("COURSE_NAME", "").strip() or "Default"
        db.register_directory(name, str(p))
        logger.info("Auto-registered legacy output dir %s as '%s'", p, name)
    finally:
        db.close()
```

Then wire it into FastAPI startup. Replace the existing app definition block to add a startup handler:

```python
@app.on_event("startup")
def _on_startup() -> None:
    auto_register_legacy_output_dir()
```

(Add the decorator under the `app.add_middleware(...)` block before the route registrations.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_startup_migration.py -v`
Expected: All three tests PASS.

- [ ] **Step 5: Run full backend suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/tui_transcript/api/main.py tests/test_startup_migration.py
git commit -m "$(cat <<'EOF'
Auto-register legacy MARKDOWN_OUTPUT_DIR on first startup

When the directories registry is empty and the env points at an existing
folder, register it once with COURSE_NAME (or 'Default') so existing
users keep their workflow on first open of the web UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update frontend api/client.ts types

**Files:**
- Modify: `frontend/src/api/client.ts:3-19, 85-98`

- [ ] **Step 1: Update the Config types**

In `frontend/src/api/client.ts`, replace the `Config` and `ConfigUpdate` interfaces (lines 3-19) and the `startTranscription` signature (lines 85-98).

Old `Config`/`ConfigUpdate`:
```ts
export interface Config {
  deepgram_api_key: string;
  naming_mode: string;
  prefix: string;
  course_name: string;
  markdown_output_dir: string;
  anthropic_api_key: string;
}

export interface ConfigUpdate {
  deepgram_api_key?: string;
  naming_mode?: string;
  prefix?: string;
  course_name?: string;
  markdown_output_dir?: string;
  anthropic_api_key?: string;
}
```

New:
```ts
export interface Config {
  deepgram_api_key: string;
  naming_mode: string;
  prefix: string;
  anthropic_api_key: string;
}

export interface ConfigUpdate {
  deepgram_api_key?: string;
  naming_mode?: string;
  prefix?: string;
  anthropic_api_key?: string;
}
```

Old `startTranscription`:
```ts
export async function startTranscription(
  fileSpecs: FileSpec[]
): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: fileSpecs }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start transcription');
  }
  return res.json();
}
```

New:
```ts
export async function startTranscription(
  fileSpecs: FileSpec[],
  directoryId: number
): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: fileSpecs, directory_id: directoryId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start transcription');
  }
  return res.json();
}
```

- [ ] **Step 2: Verify the typecheck still passes for everything not yet updated**

Run: `cd frontend && npx tsc -b 2>&1 | head -50`
Expected: Errors in `pages/Config.tsx` and `pages/Dashboard.tsx` (callers using old shape). These are intentional and will be fixed in subsequent tasks. Note them for context.

- [ ] **Step 3: Commit (despite known callers being broken — they will be fixed in tasks 7-10)**

```bash
git add frontend/src/api/client.ts
git commit -m "$(cat <<'EOF'
Drop output dir/course name from Config; require directoryId on start

Frontend type surface now matches the backend. Page-level callers
(Config, Dashboard) will be updated in the following tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Extract DirectoryForm shared component

**Files:**
- Create: `frontend/src/components/DirectoryForm.tsx`

- [ ] **Step 1: Create the shared component**

Create `frontend/src/components/DirectoryForm.tsx`:

```tsx
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { FolderSearch } from 'lucide-react';
import {
  createDirectory,
  pickDirectory,
  type DirectoryEntry,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface DirectoryFormProps {
  onSubmit: (entry: DirectoryEntry) => void;
  onCancel: () => void;
  /** Optional name suffix used to disambiguate input ids when this form is rendered multiple times on the same page. */
  idPrefix?: string;
}

export function DirectoryForm({ onSubmit, onCancel, idPrefix = 'dir' }: DirectoryFormProps) {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');

  const mutation = useMutation({
    mutationFn: () => createDirectory(name.trim(), path.trim()),
    onSuccess: (entry) => {
      onSubmit(entry);
      setName('');
      setPath('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !path.trim()) return;
    mutation.mutate();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-name`} className="text-xs">
          Name
        </Label>
        <Input
          id={`${idPrefix}-name`}
          type="text"
          placeholder="e.g. Lecture Notes"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-8 text-sm"
          autoFocus
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-path`} className="text-xs">
          Directory Path
        </Label>
        <div className="flex gap-2">
          <Input
            id={`${idPrefix}-path`}
            type="text"
            placeholder="/Users/you/Documents/transcripts"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="h-8 text-sm flex-1"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 shrink-0"
            onClick={async () => {
              try {
                const picked = await pickDirectory();
                if (picked) setPath(picked);
              } catch (err) {
                alert((err as Error).message);
              }
            }}
          >
            <FolderSearch className="size-3.5 mr-1.5" />
            Browse
          </Button>
        </div>
      </div>
      <div className="flex gap-2 items-center">
        <Button
          type="submit"
          size="sm"
          disabled={mutation.isPending || !name.trim() || !path.trim()}
        >
          {mutation.isPending ? 'Adding...' : 'Add'}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        {mutation.isError && (
          <span className="text-xs text-destructive">
            {(mutation.error as Error).message}
          </span>
        )}
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc -b 2>&1 | grep -E "DirectoryForm" || echo "OK"`
Expected: No errors specific to DirectoryForm.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DirectoryForm.tsx
git commit -m "$(cat <<'EOF'
Add shared DirectoryForm component

Encapsulates the Name + Path + Browse form used to register an output
directory. Will be consumed by both the Documents page and the new
Transcribe class selector.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Refactor Documents.tsx to use DirectoryForm

**Files:**
- Modify: `frontend/src/pages/Documents.tsx`

- [ ] **Step 1: Replace inline form with shared component**

In `frontend/src/pages/Documents.tsx`:

1. Add the import near the top with the other imports:
```tsx
import { DirectoryForm } from '@/components/DirectoryForm';
```

2. In the `Documents` component, remove the local `addName`, `addPath`, `addMutation`, `handleAdd` state/handlers (lines ~356-374) and replace the entire `{showAdd && (...)}` block (lines ~395-477) with:

```tsx
{showAdd && (
  <Card>
    <CardHeader className="p-4">
      <CardTitle className="text-sm">Register Output Directory</CardTitle>
    </CardHeader>
    <CardContent className="p-4 pt-0">
      <DirectoryForm
        idPrefix="docs-add"
        onSubmit={() => {
          queryClient.invalidateQueries({ queryKey: ['directories'] });
          setShowAdd(false);
        }}
        onCancel={() => setShowAdd(false)}
      />
    </CardContent>
  </Card>
)}
```

3. Remove the now-unused `useMutation` and `createDirectory` imports if no other code in the file still needs them. (Check: `useMutation` is still used by `removeMutation` in `DirectoryCard`, so keep it. `createDirectory` is no longer used here — remove it from the import list at line 17-30.)

4. Remove the now-unused `addName`/`addPath`/`addMutation`/`handleAdd` declarations from the `Documents` component body (the chunk around lines 357-374).

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc -b 2>&1 | grep -E "Documents" || echo "OK"`
Expected: No errors in Documents.tsx.

- [ ] **Step 3: Manual smoke test**

Run dev server (background) and visit http://localhost:5173/documents. Click "Add Directory", verify the form looks the same, that browse works, that submitting a valid path creates a new directory in the list, and Cancel hides the form. Then close the dev server.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Documents.tsx
git commit -m "$(cat <<'EOF'
Use shared DirectoryForm in Documents page

No behavior change; lays the groundwork for reusing the same form on the
Transcribe page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Add Class selector to Dashboard (Transcribe view)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add the Class card and wire it into transcription start**

In `frontend/src/pages/Dashboard.tsx`:

1. Update imports — add:
```tsx
import { getDirectories, type DirectoryEntry } from '@/api/client';
import { DirectoryForm } from '@/components/DirectoryForm';
import { Plus } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
```
(`Select*` are likely already imported — check and don't duplicate.)

2. Inside the `Dashboard` component, add new state and a directories query right after `const { data: config }` line:

```tsx
const queryClient = useQueryClient();
const { data: directories = [] } = useQuery({
  queryKey: ['directories'],
  queryFn: getDirectories,
});

const [directoryId, setDirectoryId] = useState<number | null>(() => {
  const stored = localStorage.getItem('transcribe.lastDirectoryId');
  return stored ? Number(stored) : null;
});
const [showNewClass, setShowNewClass] = useState(false);

useEffect(() => {
  if (directoryId != null) {
    localStorage.setItem('transcribe.lastDirectoryId', String(directoryId));
  }
}, [directoryId]);
```

(Add `useEffect` and `useQueryClient` to the existing `react` / `@tanstack/react-query` imports.)

3. Update the `start` function: after the `if (!config?.deepgram_api_key ...)` check, add:

```tsx
if (directoryId == null) {
  alert('Select a class first.');
  return;
}
const dir = directories.find((d) => d.id === directoryId);
if (!dir || !dir.exists) {
  alert('Selected class folder is missing — re-attach it in Documents.');
  return;
}
```

4. Update the call to `startTranscription`:

Old:
```tsx
const { session_id } = await startTranscription(specs);
```

New:
```tsx
const { session_id } = await startTranscription(specs, directoryId);
```

5. Insert the Class card into the JSX, immediately above the drop zone (the `<div ... onDrop ...>` block). Add this after the header `<div>` block:

```tsx
<Card>
  <CardHeader className="pb-3">
    <CardTitle className="text-base">Class</CardTitle>
  </CardHeader>
  <CardContent className="space-y-3">
    <div className="flex items-center gap-2">
      <Select
        value={directoryId != null ? String(directoryId) : ''}
        onValueChange={(v) => setDirectoryId(Number(v))}
        disabled={processing}
      >
        <SelectTrigger className="flex-1">
          <SelectValue placeholder="Select a class..." />
        </SelectTrigger>
        <SelectContent>
          {directories
            .filter((d: DirectoryEntry) => d.exists)
            .map((d: DirectoryEntry) => (
              <SelectItem key={d.id} value={String(d.id)}>
                {d.name}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setShowNewClass((v) => !v)}
        disabled={processing}
      >
        <Plus className="size-4 mr-1.5" />
        New class
      </Button>
    </div>
    {showNewClass && (
      <div className="rounded-md border p-3">
        <DirectoryForm
          idPrefix="transcribe-add"
          onSubmit={(entry) => {
            queryClient.invalidateQueries({ queryKey: ['directories'] });
            setDirectoryId(entry.id);
            setShowNewClass(false);
          }}
          onCancel={() => setShowNewClass(false)}
        />
      </div>
    )}
  </CardContent>
</Card>
```

6. Replace the existing `<p className="text-sm text-muted-foreground">Output: Local Markdown</p>` line in the header — drop it entirely, since the Class card now communicates the destination.

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc -b 2>&1 | grep -E "Dashboard" || echo "OK"`
Expected: No errors in Dashboard.tsx.

- [ ] **Step 3: Manual smoke test**

Start the backend and frontend dev servers (use existing background tasks if running, else `cd frontend && npm run dev` and `.venv/bin/python -m tui_transcript.api.main`). Visit http://localhost:5173.

Verify:
1. Class dropdown populates with existing directories.
2. Selecting a class persists to localStorage (check via DevTools).
3. "+ New class" expands the form; creating a new class adds it to the dropdown and auto-selects it.
4. Clicking Start with no class selected shows the alert.
5. A full transcription writes the markdown into the chosen class folder.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "$(cat <<'EOF'
Add Class selector card to Transcribe view

Dropdown of registered directories with inline 'New class' form. The
selection is required before Start, persists across reloads, and is
forwarded to /api/transcription/start as directory_id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Remove output dir + course name fields from Settings

**Files:**
- Modify: `frontend/src/pages/Config.tsx`

- [ ] **Step 1: Strip the dropped fields**

In `frontend/src/pages/Config.tsx`:

1. Remove the unused imports `FolderOpen`, `FolderSearch`, `openPath`, `pickDirectory` from the import block at the top — they were only used by the markdown_output_dir field.

2. Remove the `if (!(values.course_name ?? '').trim())` validation block in `handleSubmit`.

3. In the `update` build, remove the `course_name` and `markdown_output_dir` lines.

4. Remove both the entire `<div className="space-y-2">` block for `Markdown Output Directory` (Label + flex with Input + Browse + Open buttons) and the `<div className="space-y-2">` block for `Course Name *`.

After cleanup, the form should contain only: Deepgram key, Anthropic key, Naming Mode, Prefix, Save button.

5. Update the `handleSubmit` function so it now reads cleanly:

```tsx
const handleSubmit = (e: React.FormEvent) => {
  e.preventDefault();
  const update: ConfigUpdate = {};
  if (form.deepgram_api_key !== undefined) update.deepgram_api_key = form.deepgram_api_key;
  if (form.naming_mode !== undefined) update.naming_mode = form.naming_mode;
  if (form.prefix !== undefined) update.prefix = form.prefix;
  if (form.anthropic_api_key !== undefined) update.anthropic_api_key = form.anthropic_api_key;
  mutation.mutate(update);
};
```

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc -b 2>&1`
Expected: No errors.

- [ ] **Step 3: Manual smoke test**

Visit http://localhost:5173/config. Verify the form shows only the four remaining fields, that Save still works, and that no leftover icons/buttons reference the removed fields.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Config.tsx
git commit -m "$(cat <<'EOF'
Remove output directory and course name fields from Settings

These are now per-class, set via the Class selector on the Transcribe
view. The env-backed config still carries the old values for the TUI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: End-to-end verification

**Files:** none — manual + suite re-run.

- [ ] **Step 1: Re-run the full backend test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Production typecheck the frontend**

Run: `cd frontend && npx tsc -b`
Expected: Exit code 0, no errors.

- [ ] **Step 3: Production frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Manual end-to-end browser walk-through**

With both servers running:

1. Open http://localhost:5173 — confirm the new Class card is the first thing under the page title.
2. Drag in a small audio/video file. Click Start without selecting a class — confirm "Select a class first." alert.
3. Pick an existing class from the dropdown. Click Start — confirm the file transcribes and the resulting `.md` lands in that class's folder.
4. Click "+ New class". Enter a name and pick a fresh path with Browse. Click Add. Confirm the new entry is auto-selected.
5. Reload the page. Confirm the dropdown defaults to the last-selected class.
6. Visit Documents — confirm both classes are listed.
7. Visit Settings — confirm output directory and course name fields are gone, that Save still persists the four remaining fields.

- [ ] **Step 5: Final summary commit (optional, only if anything was touched during verification)**

If steps 1-4 surfaced no changes, no commit needed. If they did, fix and commit using a descriptive message.

---

## Notes

- The pipeline still calls `DocumentStore.ensure_registered(effective_output_dir)` after a successful export. When `output_dir` is supplied by the API, that directory is already registered (we resolved it from the same registry), so `ensure_registered` is a no-op for that path. No change required.
- `tests/conftest.py` already provides a `db` fixture; new tests that need raw DB access can rely on it where convenient.
- Keep an eye on stale React Query cache: invalidating `['directories']` after `createDirectory` is what makes the new entry show up in both the Dashboard dropdown and the Documents list.
