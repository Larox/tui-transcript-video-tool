# Phase 1: Content Organization — Design Spec

## Overview

Add a Collections layer to organize transcripts by course, mentorship, tutorship, or any user-defined grouping. Add tags for cross-cutting classification and full-text search across all transcripts.

## Data Model

### Collections
- `id` (INTEGER PK)
- `name` (TEXT, e.g. "Machine Learning Course", "Design Mentorship")
- `collection_type` (TEXT: "course", "mentorship", "tutorship", "academic", "other")
- `description` (TEXT, optional)
- `created_at`, `updated_at` (TEXT, ISO datetime)

### Collection Items (many-to-many: collection <-> processed_videos)
- `id` (INTEGER PK)
- `collection_id` (FK -> collections)
- `video_id` (FK -> processed_videos)
- `position` (INTEGER, for ordering within collection)
- `added_at` (TEXT)

### Tags
- `id` (INTEGER PK)
- `name` (TEXT UNIQUE, e.g. "python", "design-patterns")
- `color` (TEXT, hex color for UI)

### Video Tags (many-to-many: tags <-> processed_videos)
- `video_id` (FK -> processed_videos)
- `tag_id` (FK -> tags)

### Full-Text Search (FTS5)
- Virtual table `transcript_search` indexing: `output_title`, `source_path`, `transcript_content`
- Populated when a transcription completes (pipeline hook)
- Markdown content read from output_path on indexing

## API Endpoints

### Collections
- `GET /api/collections` — list all collections with item counts
- `POST /api/collections` — create a collection
- `GET /api/collections/{id}` — get collection with its items (transcripts)
- `PUT /api/collections/{id}` — update name/type/description
- `DELETE /api/collections/{id}` — delete collection (not the transcripts)
- `POST /api/collections/{id}/items` — add transcript(s) to collection
- `DELETE /api/collections/{id}/items/{video_id}` — remove transcript from collection
- `PUT /api/collections/{id}/items/reorder` — reorder items

### Tags
- `GET /api/tags` — list all tags
- `POST /api/tags` — create a tag
- `DELETE /api/tags/{id}` — delete a tag
- `POST /api/videos/{video_id}/tags` — add tag to transcript
- `DELETE /api/videos/{video_id}/tags/{tag_id}` — remove tag

### Search
- `GET /api/search?q=term&collection_id=&tag=` — full-text search with optional filters

## Frontend

### Collections Page (`/collections`)
- Grid/list of collections with type badge, item count, description preview
- Create collection dialog (name, type, description)
- Click into collection -> detail view showing ordered transcripts
- Drag-to-reorder items within a collection (stretch goal, basic reorder first)

### Sidebar Update
- Add "Collections" nav item between "Transcribe" and "Documents"

### Search
- Global search bar in the header
- Results show transcript title, collection, matching excerpt, tags

### Tag UI
- Tag pills on transcript cards (colored dots)
- Tag filter dropdown on Collections detail and Documents pages

## Pipeline Integration

When a transcription completes:
1. Index the transcript content in FTS5
2. If the user set a collection before starting, auto-add to that collection

## Testing

- Unit tests for CollectionStore CRUD (create, list, add items, remove, reorder)
- Unit tests for search indexing and querying
- API endpoint tests using FastAPI TestClient
- Integration test: transcribe -> assign to collection -> search -> find
