# Web Interface Migration Plan

This document outlines the plan to add a React web interface alongside the existing TUI, keeping Python for the backend and enabling complex user interactions on the web.

---

## 1. Current Architecture Summary

### What's Already Well-Separated

| Layer | Location | UI Coupling |
|-------|----------|-------------|
| **Models** | `models.py` | None – pure dataclasses |
| **Transcription** | `services/transcription.py` | None – accepts `on_status` callback |
| **History** | `services/history.py` | None – pure SQLite |
| **Google Docs** | `services/google_docs.py` | None |
| **Markdown Export** | `services/markdown_export.py` | None |

### What's TUI-Coupled

| Component | Coupling |
|-----------|----------|
| **Dashboard pipeline** | `_run_pipeline()` mixes business logic with Textual widgets (`_log`, `_refresh_jobs`, `status_label.update`) |
| **Config** | Reads/writes `.env` file; TUI-specific flow |
| **File selection** | Local filesystem paths; TUI uses `Path` objects |

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SHARED CORE (Python)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  models.py (serializable for API)                                        │
│  services/transcription.py                                                │
│  services/history.py                                                      │
│  services/google_docs.py                                                  │
│  services/markdown_export.py                                              │
│  services/pipeline.py  ← NEW: extracted pipeline logic                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│  TUI (Textual)                 │   │  Web API (FastAPI)              │
│  - app.py                      │   │  - REST endpoints              │
│  - screens/*                   │   │  - WebSocket/SSE for progress  │
│  - Uses pipeline via callbacks │   │  - File upload handling        │
└───────────────────────────────┘   └───────────────────────────────┘
                                                    │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │  React Frontend                 │
                                    │  - SPA with complex UX          │
                                    │  - Real-time progress           │
                                    │  - Drag & drop, multi-select    │
                                    └───────────────────────────────┘
```

---

## 3. Implementation Phases

### Phase 1: Extract Pipeline Logic (Backend Refactor)

**Goal:** Make the transcription → export pipeline reusable by both TUI and web.

1. **Create `services/pipeline.py`**
   - Extract the core logic from `DashboardScreen._run_pipeline()`
   - Accept an async generator or callback interface for progress/status updates
   - Input: `(config: AppConfig, jobs: list[VideoJob], callbacks)`
   - Callbacks: `on_job_status(job, status)`, `on_log(msg)`, `on_progress(current, total)`

2. **Make models API-friendly**
   - Add `VideoJob.from_path(path: Path)` and `VideoJob.to_dict()` / `from_dict()` for JSON serialization
   - Use `str` for paths in API payloads; convert to `Path` only in services

3. **Config abstraction**
   - Create `ConfigStore` interface: `load() -> AppConfig`, `save(config: AppConfig) -> None`
   - TUI implementation: reads/writes `.env`
   - Web implementation: per-user config in DB or session (see Phase 3)

4. **Refactor `DashboardScreen`**
   - Call `pipeline.run(config, jobs, callbacks)` instead of inline logic
   - Map callbacks to TUI updates (`_log`, `_refresh_jobs`, etc.)

---

### Phase 2: Add FastAPI Backend

**Goal:** Expose the same capabilities via HTTP for the React frontend.

1. **Create `src/tui_transcript/api/`**
   - `main.py` – FastAPI app entry
   - `routes/config.py` – GET/PUT config (user-scoped or global)
   - `routes/jobs.py` – POST jobs (file upload), GET job status
   - `routes/transcription.py` – POST start transcription, GET progress (SSE)

2. **File upload handling**
   - Accept `multipart/form-data` with video files
   - Store in temp directory; pass paths to pipeline
   - Clean up temp files after processing

3. **Progress streaming**
   - Use **Server-Sent Events (SSE)** or **WebSockets** for real-time job progress
   - Pipeline callbacks push to an in-memory queue; SSE endpoint reads from it

4. **CORS**
   - Enable CORS for React dev server (e.g. `http://localhost:5173`)

5. **Dependencies**
   - Add `fastapi`, `uvicorn`, `python-multipart` to `pyproject.toml`

---

### Phase 3: React Frontend

**Goal:** Rich web UI with complex interactions.

1. **Scaffold React app**
   - Use Vite + React + TypeScript
   - Suggested folder: `frontend/` at project root

2. **Core features**
   - **Config page** – form for Deepgram key, Google credentials, naming, output dir
   - **Dashboard** – file list, language selector, start/clear
   - **File upload** – drag & drop, multi-select, progress per file
   - **Real-time progress** – SSE/WebSocket for transcription status

3. **Complex interactions (future)**
   - Drag & drop reorder of jobs
   - Inline transcript preview/edit before export
   - Batch operations (e.g. change language for all)
   - History view with download links

4. **State management**
   - React Query (TanStack Query) for API calls
   - Zustand or Context for UI state

---

### Phase 4: Config & Auth for Web

**Goal:** Secure, multi-user config for web.

1. **Config storage**
   - Option A: Single config (like TUI) – store in DB or env, no auth
   - Option B: Per-user config – requires auth (e.g. simple API key, or OAuth)

2. **Google credentials**
   - TUI: path to JSON file
   - Web: JSON file upload → store in temp or secure storage; or use OAuth for Drive

3. **Deepgram key**
   - Store server-side (encrypted if multi-user); never expose to client

---

## 4. Suggested Project Layout After Migration

```
tui_transcript_cursor/
├── src/
│   └── tui_transcript/
│       ├── __init__.py
│       ├── models.py              # Shared
│       ├── app.py                  # TUI entry (unchanged entry point)
│       ├── services/
│       │   ├── transcription.py   # Shared
│       │   ├── history.py         # Shared
│       │   ├── google_docs.py     # Shared
│       │   ├── markdown_export.py # Shared
│       │   ├── pipeline.py        # NEW – shared pipeline
│       │   └── config_store.py    # NEW – config abstraction
│       ├── screens/               # TUI-only
│       │   ├── config.py
│       │   ├── dashboard.py       # Refactored to use pipeline
│       │   └── file_picker.py
│       └── api/                   # NEW – web API
│           ├── __init__.py
│           ├── main.py
│           ├── routes/
│           │   ├── config.py
│           │   ├── jobs.py
│           │   └── transcription.py
│           └── dependencies.py
├── frontend/                      # NEW – React app
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Config.tsx
│   │   │   └── Dashboard.tsx
│   │   ├── components/
│   │   ├── api/
│   │   └── hooks/
│   └── ...
├── docs/
│   └── WEB_INTERFACE_MIGRATION_PLAN.md
├── pyproject.toml
└── README.md
```

---

## 5. API Design Sketch

### Config

```http
GET  /api/config          → AppConfig (masked keys)
PUT  /api/config          → Update config (body: AppConfig)
```

### Jobs / Transcription

```http
POST /api/jobs/upload     → Upload files (multipart), returns job IDs
GET  /api/jobs            → List jobs with status
POST /api/transcription/start  → Start pipeline for pending jobs
GET  /api/transcription/progress  → SSE stream of progress events
```

### Progress (SSE)

```
event: job_status
data: {"job_id": "...", "status": "transcribing", "progress": 0.5}

event: log
data: {"message": "Transcribing video.mp4..."}

event: done
data: {"job_id": "...", "doc_url": "https://..."}
```

---

## 6. Key Decisions to Make

| Decision | Options | Recommendation |
|----------|---------|----------------|
| **API framework** | FastAPI, Flask, Starlette | FastAPI – async, auto docs, type hints |
| **Progress streaming** | SSE vs WebSocket | SSE – simpler, one-way, fits progress use case |
| **Web config** | Single vs multi-user | Start single; add auth later if needed |
| **Google JSON on web** | Upload path vs paste JSON | Upload file → store in temp; use for that session |
| **Monorepo** | Single repo vs separate | Single repo – `frontend/` + `src/` |

---

## 7. Migration Order

1. **Phase 1** – Extract pipeline, refactor TUI to use it. Verify TUI still works.
2. **Phase 2** – Add FastAPI, implement config + upload + transcription endpoints. Test with curl/Postman.
3. **Phase 3** – Scaffold React, implement config + dashboard + upload flows. Connect to API.
4. **Phase 4** – Add auth/config storage if needed.

---

## 8. Run Commands (After Implementation)

```bash
# TUI (unchanged)
uv run tui-transcript

# Web API
uv run uvicorn tui_transcript.api.main:app --reload

# React dev server
cd frontend && npm run dev
```

---

## 9. Summary

The existing services are already well-isolated. The main work is:

1. **Extract** the pipeline from the dashboard into a reusable service.
2. **Add** a FastAPI layer that exposes the same pipeline via HTTP + file upload.
3. **Build** a React frontend that consumes the API.
4. **Abstract** config storage so TUI uses `.env` and web can use DB/session.

This approach keeps the TUI fully functional while adding a modern web interface for users who need richer interactions.
