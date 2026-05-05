# Learning Tool — Design Spec

**Date:** 2026-05-05
**Status:** Approved
**Linear Project:** [learning tool](https://linear.app/sebasprojects/project/learning-tool-5267d79561d8)

---

## Overview

A web-based study tool for online students with limited time. Students upload recorded class videos, the tool transcribes them and generates structured study materials, so they can learn from the content without watching the videos.

**Core premise:** The transcript is the source of truth. Everything else (summary, Q&A, flashcards, action items) is derived from it.

---

## Approach

Extend the existing `tui-transcript-video-tool` codebase:

- **Keep:** FastAPI backend, transcription pipeline (Deepgram + Whisper), SQLite FTS5 search, collections/tags, key moments service
- **Add:** Content generation services, new DB tables, new API routes, rebuilt React frontend
- **Deprecate gradually:** TUI (eventually replaced by CLI or MCP for agent workflows)
- **Not yet:** Multi-user auth (architecture must not assume single user, but auth is not built in this phase)

---

## Pages

| Page | Purpose |
|---|---|
| **Dashboard** | Priority view: urgent action items and alerts across all courses |
| **Mis Materias** | Grid of all courses with last activity date |
| **Materia → Clases** | List of classes for a course, with status and date |
| **Clase** | Full study view: summary, outline, Q&A, flashcards, action items |
| **Subir Clase** | Upload video, select course, real-time transcription + generation progress |

---

## Class Detail View (per class)

When a student opens a class, they see:

1. **Resumen ejecutivo** — 200-400 word summary of what was covered
2. **Outline con timestamps** — list of topics in order with video timestamp links (e.g., "00:12:30 — Introduction to derivatives")
3. **Action Items / Alertas** — urgent things extracted from the class (deadline changes, homework, "for next class we need X")
4. **Q&A** — 10 question-answer pairs covering key concepts
5. **Flashcards** — 20 concept/definition pairs for review

---

## Action Items

Extracted by Claude from the transcript. Each item has:

- `text` — what was said
- `urgency` — `high` / `medium` / `low`
- `extracted_date` — date mentioned in transcript if any (e.g. "for Friday")
- `course_id` + `class_id` — origin

The Dashboard aggregates action items across all courses, ordered by urgency and extracted date.

---

## Course Organization

- **Primary:** Course → Classes hierarchy (Finanzas → Clase 1, Clase 2...)
- **Secondary:** Tags as cross-cutting labels (e.g., "macroeconomía" on both a Finance and Economics class)
- Tags map directly to the existing tag system in the codebase

---

## Upload & Processing Flow

```
Student uploads video
  → POST /api/upload              (save temp file)
  → POST /api/transcription/start (select engine: Deepgram or Whisper)
  → SSE  /api/transcription/progress/{session_id}
      transcription complete → saved to DB
  → POST /api/classes/{id}/generate
  → SSE  /api/generation/progress/{class_id}
      Claude generates: summary → Q&A → flashcards → action_items
      each artifact saved to DB as completed
  → Class status: ready
```

**Class status states:** `pending` → `transcribing` → `generating` → `ready` | `error`

---

## Backend Changes (additive)

### New Services

| File | Purpose |
|---|---|
| `services/content_generator.py` | Claude API calls: summary, Q&A, flashcards, action items |
| `services/alert_store.py` | Store and query action items with urgency + date |

### New DB Tables

| Table | Fields |
|---|---|
| `summaries` | id, class_id, text, generated_at |
| `qa_pairs` | id, class_id, question, answer, order |
| `flashcards` | id, class_id, concept, definition, order |
| `action_items` | id, class_id, text, urgency, extracted_date, dismissed |

### New API Routes

| Route | Purpose |
|---|---|
| `POST /api/classes/{id}/generate` | Trigger content generation (SSE) |
| `GET /api/classes/{id}/summary` | Get summary |
| `GET /api/classes/{id}/qa` | Get Q&A pairs |
| `GET /api/classes/{id}/flashcards` | Get flashcards |
| `GET /api/classes/{id}/action-items` | Get action items for a class |
| `GET /api/dashboard/alerts` | All undismissed action items across courses |

### Fix Required

- `api/state.py`: Replace in-memory session storage with SQLite-backed sessions (TTL + cleanup)

---

## Frontend Stack

Rebuild with existing stack: React 19 + TypeScript + Tailwind + shadcn/ui + TanStack Query + SSE for real-time progress.

---

## Multi-User Readiness

No auth is built in this phase, but:
- DB schema uses `user_id` foreign keys (nullable for now)
- No hardcoded single-user assumptions anywhere
- Routes structured so permission middleware can be added later without rewrites

---

## Out of Scope (this phase)

- User registration / login / auth
- Multi-student collaboration
- Instructor role / course sharing
- Mobile app
- TUI removal
- Export to Google Docs
