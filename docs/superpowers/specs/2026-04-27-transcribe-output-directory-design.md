# Per-Class Output Directory in Transcribe View

**Date:** 2026-04-27
**Status:** Approved, ready for implementation plan

## Problem

Today the markdown output directory and course name are configured globally
in Settings (env-backed: `MARKDOWN_OUTPUT_DIR`, `COURSE_NAME`). Every batch of
videos lands in the same folder with the same course metadata. In practice each
batch of videos belongs to one class, so the destination should be chosen
per-batch from the Transcribe view — same pattern as registering an output
directory from the Documents view.

## Goals

- User picks a destination "class" directory directly in the Transcribe view
  before starting a batch.
- Existing registered directories appear in a dropdown; a new class can be
  created inline using the same Name + Path + Browse form pattern as the
  Documents page.
- The directory's name doubles as the `course_name` written into the markdown
  frontmatter — one source of truth.
- Settings no longer surfaces `markdown_output_dir` or `course_name`. The TUI
  continues to read env-based config so its workflow is unaffected.

## Non-goals

- Multiple courses per directory (1 directory = 1 class).
- A separate slug/display-name distinction for course names. If we ever need a
  slugged value in frontmatter, derive it from `name` at write time.
- Migrating the TUI app's UX. The TUI continues to use env config as before.
- Renaming or moving existing markdown files when a directory's name changes.

## Data Model

`directories` table (SQLite, in `HistoryDB`) is unchanged structurally. The
existing `name` column doubles as the course name. No migration needed.

When the pipeline writes a markdown file, `course_name` in the frontmatter is
sourced from the chosen directory's `name` (instead of `config.course_name`).

## Backend Changes

### `services/pipeline.py`

`run_pipeline` accepts an optional override for output destination and course
name:

```python
async def run_pipeline(
    config: AppConfig,
    jobs: list[VideoJob],
    callbacks: PipelineCallbacks | None = None,
    output_dir: Path | None = None,
    course_name: str | None = None,
) -> None: ...
```

When `output_dir` is provided, it is used in place of
`config.markdown_output_dir`; otherwise the existing config value is used
(preserves TUI behavior). Same for `course_name`.

Auto-registration via `DocumentStore.ensure_registered` is skipped when
`output_dir` is provided, because the directory was selected from a known
registered entry.

### `api/routes/transcription.py`

`TranscriptionStartRequest` (in `schemas.py`) gains a required field:

```python
directory_id: int
```

`POST /transcription/start`:
1. Look up the directory via `DocumentStore` / `HistoryDB`.
2. 404 if not found, 422 if path no longer exists on disk (with the standard
   "Please re-attach" message used elsewhere).
3. Pass `output_dir=Path(entry["path"])` and `course_name=entry["name"]` into
   `run_pipeline`.

### `api/routes/documents.py`

No changes. The existing `POST /documents/directories` endpoint already
handles inline create with Name + Path validation.

### `api/routes/config.py` and `api/schemas.py`

Remove `markdown_output_dir` and `course_name` from the API-level `Config`
and `ConfigUpdate` Pydantic schemas. The internal `AppConfig` dataclass
(`models.py`) and `EnvConfigStore` keep both fields so the TUI and pipeline
defaults still work — only the web API surface shrinks.

## Frontend Changes

### Transcribe view (`pages/Dashboard.tsx`)

Add a "Class" card above the drop zone:

```
┌─ Class ───────────────────────────────────────┐
│ [ Lecture Notes – Algorithms              ▼ ] │
│  + New class                                  │
└───────────────────────────────────────────────┘
```

- Dropdown sourced from `getDirectories()` via React Query. Sorted by
  `created_at desc` so the most recent class is at top.
- Selected `directory_id` persists in `localStorage` under
  `transcribe.lastDirectoryId` so re-opening the page defaults to the last
  used class.
- "+ New class" expands an inline form (Name + Path + Browse) identical to
  the Documents page form. Form is extracted into a shared component (see
  below) so both pages use the same UI.
- On submit: calls `createDirectory`, refreshes the directories query,
  auto-selects the new entry, collapses the form.
- Directories where `exists === false` are shown with the warning style
  already used in Documents and are not selectable.

`startTranscription` is updated to send `directory_id`. The Start button
remains enabled regardless of selection; if no directory is selected when
clicked, surface an inline error in the same place as the existing "Configure
your Deepgram API key in Settings first" alert.

### Shared component: `components/DirectoryForm.tsx`

Extract the existing form body from `pages/Documents.tsx` (lines ~395–477)
into a reusable component with this surface:

```ts
interface DirectoryFormProps {
  onSubmit: (entry: DirectoryEntry) => void;
  onCancel: () => void;
}
```

Both `Documents.tsx` and the new Transcribe-view "+ New class" expansion use
this component. No behavioral change to the Documents page beyond the
refactor.

### Settings view (`pages/Config.tsx`)

Remove the Output Directory and Course Name fields. Update copy if needed so
the page still reads coherently with the remaining fields (Deepgram key,
Anthropic key, naming mode, prefix).

### `api/client.ts`

- `Config` / `ConfigUpdate` lose `markdown_output_dir` and `course_name`.
- `FileSpec` is unchanged.
- `startTranscription` signature gains `directoryId: number` and the request
  body includes `directory_id`.

## Migration / Backwards Compatibility

- **Existing directories**: already have a `name` value, which becomes their
  course name automatically. No DB migration required.
- **First-run with legacy env**: on app startup, if `MARKDOWN_OUTPUT_DIR` is
  set in the environment AND no directories are registered, the API
  auto-registers it once with name = `COURSE_NAME` (or "Default" if empty).
  This means existing users do not have to recreate their setup.
- **TUI**: continues to read `MARKDOWN_OUTPUT_DIR` and `COURSE_NAME` from env
  via `EnvConfigStore`. No code change to the TUI app.

## Error Handling

| Scenario | Behavior |
| --- | --- |
| User clicks Start with no directory selected | Inline error: "Select a class first." |
| Selected directory's path no longer exists on disk | API returns 422; frontend shows "Class folder missing — re-attach in Documents." |
| Inline create fails (path invalid) | Form shows existing 422 error inline (same as Documents). |
| Backend receives invalid `directory_id` | 404 from `/transcription/start`. |

## Testing

- `tests/test_transcription.py` (extend or create):
  - `start_transcription` requires `directory_id`; missing → 422.
  - Unknown `directory_id` → 404.
  - Directory whose path was deleted → 422 with re-attach message.
  - Successful run writes markdown into the chosen directory and frontmatter
    `course_name` matches the directory's `name`.
- `tests/test_api.py` (Config endpoint):
  - `markdown_output_dir` and `course_name` no longer present in `GET /config`
    response or accepted by `PUT /config`.
- Existing `tests/test_collections.py` and `tests/test_search.py` should not
  be affected.
- Manual: walk through the Transcribe view in the browser end-to-end with one
  existing class and one newly-created class.

## Out of Scope

- A class detail page (per-class transcripts overview) — Documents already
  shows this.
- Bulk move of existing markdown files between classes.
- Reordering / pinning classes in the dropdown beyond default sort.
